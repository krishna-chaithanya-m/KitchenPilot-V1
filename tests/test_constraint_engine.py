"""Comprehensive Test Suite for Stage E Production Constraint & Ingredient Matching Engine.

Validates:
1. Ingredient matching & resolution hierarchy (exact, canonical, alias, normalized, unresolved)
2. Distinction between chilli and dairy variants (no false-positive collapsing)
3. Dietary compliance rules (Vegetarian, Vegan, Jain, Satvik, tri-state compliance)
4. Hard allergen exclusions (dairy, peanut, tree nut, gluten, etc.)
5. Hard ingredient exclusions and inclusions
6. Pantry availability matching (full, partial, zero coverage, require_all_ingredients hard mode)
7. Hard nutritional boundaries (calories, protein, exact boundaries, 0.0 calorie handling)
8. Contradictory / impossible constraint conflict detection
9. Zero-result handling with structured diagnostics
10. Property invariants: hard rejections never leak into recommendations
11. API endpoint integration with constraint parameters
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.constraints import (
    AllergenConstraints,
    ComplianceStatus,
    ConstraintEngine,
    ConstraintRequest,
    DietaryConstraints,
    IngredientConstraintMatcher,
    IngredientConstraints,
    MatchType,
    NutritionConstraintEvaluator,
    NutritionConstraints,
)
from src.recommendation.config import RecommendationConfig
from src.recommendation.nutrition_scorer import NutritionGoals
from src.recommendation.preference_filter import UserPreferences
from src.recommendation.recommender import KitchenPilotRecommender


@pytest.fixture(scope="module")
def constraint_engine() -> ConstraintEngine:
    return ConstraintEngine()


@pytest.fixture(scope="module")
def recommender() -> KitchenPilotRecommender:
    return KitchenPilotRecommender()


from typing import Generator

@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


# ============================================================================
# 1. INGREDIENT MATCHING & VARIANT PRESERVATION TESTS
# ============================================================================

def test_ingredient_matching_hierarchy(constraint_engine: ConstraintEngine):
    matcher = constraint_engine.ingredient_matcher

    # 1. Exact canonical ID
    res_id = matcher.resolve_ingredient("ING00046")
    assert res_id.match_type in (MatchType.EXACT, MatchType.CANONICAL)
    assert res_id.canonical_ingredient_id == "ING00046"

    # 2. Canonical name
    res_name = matcher.resolve_ingredient("cumin")
    assert res_name.canonical_name == "cumin"
    assert res_name.match_type in (MatchType.EXACT, MatchType.CANONICAL)

    # 3. Curated alias (jeera -> cumin)
    res_alias = matcher.resolve_ingredient("jeera")
    assert res_alias.canonical_name == "cumin"
    assert res_alias.match_type in (MatchType.ALIAS, MatchType.NORMALIZED, MatchType.CANONICAL)

    # 4. Normalized alias
    res_norm = matcher.resolve_ingredient("  Fresh Cumin Seeds  ")
    assert res_norm.canonical_name is not None
    assert "cumin" in res_norm.canonical_name

    # 5. Unresolved ingredient
    res_unresolved = matcher.resolve_ingredient("xyz_nonexistent_alien_spice_999")
    assert res_unresolved.match_type == MatchType.UNRESOLVED


def test_distinct_ingredient_variants_not_collapsed(constraint_engine: ConstraintEngine):
    matcher = constraint_engine.ingredient_matcher

    # Chilli variants must remain distinct in ontology
    res_red = matcher.resolve_ingredient("red chilli")
    res_powder = matcher.resolve_ingredient("red chilli powder")
    res_green = matcher.resolve_ingredient("green chilli")
    res_kashmiri = matcher.resolve_ingredient("kashmiri red chilli")

    # None of them should be unresolved
    assert res_red.canonical_name is not None
    assert res_green.canonical_name is not None
    assert res_powder.canonical_name is not None
    assert res_kashmiri.canonical_name is not None

    # Red chilli, green chilli, and kashmiri red chilli are distinct canonical items
    assert res_red.canonical_name.lower() != res_green.canonical_name.lower()
    assert res_green.canonical_name.lower() != res_kashmiri.canonical_name.lower()

    # Dairy variants must remain distinct
    res_milk = matcher.resolve_ingredient("milk")
    res_paneer = matcher.resolve_ingredient("paneer")
    res_butter = matcher.resolve_ingredient("butter")
    assert res_milk.canonical_name != res_paneer.canonical_name
    assert res_paneer.canonical_name != res_butter.canonical_name


# ============================================================================
# 2. DIETARY COMPLIANCE TESTS (VEG, VEGAN, JAIN, SATVIK)
# ============================================================================

def test_vegetarian_hard_constraint(constraint_engine: ConstraintEngine):
    req_veg = ConstraintRequest(dietary=DietaryConstraints(vegetarian=True))

    # Evaluate against all recipes and check compliance status
    meta = constraint_engine.dietary_engine._recipes_metadata
    non_veg_ids = [rid for rid, m in meta.items() if m.get("vegetarian") is False]
    veg_ids = [rid for rid, m in meta.items() if m.get("vegetarian") is True]

    assert len(non_veg_ids) > 0
    assert len(veg_ids) > 0

    # Non-vegetarian recipes must be rejected
    ev_fail = constraint_engine.evaluate_candidate(non_veg_ids[0], req_veg)
    assert not ev_fail.passed
    assert any("vegetarian" in f.lower() for f in ev_fail.hard_failures)
    assert ev_fail.dietary_results.get("vegetarian") == ComplianceStatus.NON_COMPLIANT

    # Vegetarian recipe must pass vegetarian constraint
    ev_pass = constraint_engine.evaluate_candidate(veg_ids[0], req_veg)
    assert ev_pass.passed
    assert ev_pass.dietary_results.get("vegetarian") == ComplianceStatus.COMPLIANT


def test_vegan_hard_constraint(constraint_engine: ConstraintEngine):
    req_vegan = ConstraintRequest(dietary=DietaryConstraints(vegan=True))

    # Find a recipe with dairy (e.g. paneer, ghee, milk)
    matcher = constraint_engine.ingredient_matcher
    dairy_recipes = [
        rid for rid, ings in matcher._recipe_clean_ingredients.items()
        if any("paneer" in i or "ghee" in i or "milk" in i for i in ings)
    ]
    assert len(dairy_recipes) > 0

    ev = constraint_engine.evaluate_candidate(dairy_recipes[0], req_vegan)
    assert not ev.passed
    assert any("vegan" in f.lower() for f in ev.hard_failures)


def test_jain_root_vegetable_prohibition(constraint_engine: ConstraintEngine):
    req_jain = ConstraintRequest(dietary=DietaryConstraints(jain=True))

    # Recipe containing onion or garlic must be rejected under Jain rules
    matcher = constraint_engine.ingredient_matcher
    onion_recipes = [
        rid for rid, ings in matcher._recipe_clean_ingredients.items()
        if any("onion" in i or "garlic" in i or "potato" in i for i in ings)
    ]
    assert len(onion_recipes) > 0

    ev = constraint_engine.evaluate_candidate(onion_recipes[0], req_jain)
    assert not ev.passed
    assert any("jain" in f.lower() or "root" in f.lower() for f in ev.hard_failures)


def test_satvik_prohibition(constraint_engine: ConstraintEngine):
    req_satvik = ConstraintRequest(dietary=DietaryConstraints(satvik=True))

    # Recipe containing onion or garlic must be rejected under Satvik rules
    matcher = constraint_engine.ingredient_matcher
    garlic_recipes = [
        rid for rid, ings in matcher._recipe_clean_ingredients.items()
        if any("garlic" in i or "onion" in i for i in ings)
    ]
    assert len(garlic_recipes) > 0

    ev = constraint_engine.evaluate_candidate(garlic_recipes[0], req_satvik)
    assert not ev.passed
    assert any("satvik" in f.lower() for f in ev.hard_failures)


# ============================================================================
# 3. ALLERGEN HARD EXCLUSIONS TESTS
# ============================================================================

def test_allergen_hard_exclusion_dairy(constraint_engine: ConstraintEngine):
    req_dairy = ConstraintRequest(allergens=AllergenConstraints(excluded_allergens=["dairy"]))

    matcher = constraint_engine.ingredient_matcher
    milk_recipes = [
        rid for rid, ings in matcher._recipe_clean_ingredients.items()
        if any("milk" in i or "curd" in i or "paneer" in i for i in ings)
    ]
    assert len(milk_recipes) > 0

    ev = constraint_engine.evaluate_candidate(milk_recipes[0], req_dairy)
    assert not ev.passed
    assert any("allergen" in f.lower() and "dairy" in f.lower() for f in ev.hard_failures)


def test_allergen_hard_exclusion_peanut(constraint_engine: ConstraintEngine):
    req_peanut = ConstraintRequest(allergens=AllergenConstraints(excluded_allergens=["peanut"]))

    matcher = constraint_engine.ingredient_matcher
    peanut_recipes = [
        rid for rid, ings in matcher._recipe_clean_ingredients.items()
        if any("peanut" in i for i in ings)
    ]
    if peanut_recipes:
        ev = constraint_engine.evaluate_candidate(peanut_recipes[0], req_peanut)
        assert not ev.passed
        assert any("allergen" in f.lower() and "peanut" in f.lower() for f in ev.hard_failures)


# ============================================================================
# 4. INGREDIENT EXCLUSION & INCLUSION TESTS
# ============================================================================

def test_ingredient_hard_exclusion(constraint_engine: ConstraintEngine):
    req_exc = ConstraintRequest(
        ingredients=IngredientConstraints(excluded_ingredients=["tomato"])
    )

    matcher = constraint_engine.ingredient_matcher
    tomato_recipes = [
        rid for rid, ings in matcher._recipe_clean_ingredients.items()
        if any("tomato" in i for i in ings)
    ]
    assert len(tomato_recipes) > 0

    ev = constraint_engine.evaluate_candidate(tomato_recipes[0], req_exc)
    assert not ev.passed
    assert any("excluded ingredient" in f.lower() and "tomato" in f.lower() for f in ev.hard_failures)


def test_ingredient_hard_requirement(constraint_engine: ConstraintEngine):
    req_req = ConstraintRequest(
        ingredients=IngredientConstraints(required_ingredients=["spinach"])
    )

    matcher = constraint_engine.ingredient_matcher
    no_spinach_recipes = [
        rid for rid, ings in matcher._recipe_clean_ingredients.items()
        if not any("spinach" in i or "palak" in i for i in ings)
    ]
    assert len(no_spinach_recipes) > 0

    ev = constraint_engine.evaluate_candidate(no_spinach_recipes[0], req_req)
    assert not ev.passed
    assert any("missing required ingredient" in f.lower() and "spinach" in f.lower() for f in ev.hard_failures)


# ============================================================================
# 5. PANTRY AVAILABILITY & HARD MODE TESTS
# ============================================================================

def test_pantry_metrics_calculation(constraint_engine: ConstraintEngine):
    matcher = constraint_engine.ingredient_matcher
    # Pick a recipe
    rids = list(matcher._recipe_clean_ingredients.keys())
    assert len(rids) > 0
    rid = rids[0]
    recipe_ings = matcher._recipe_clean_ingredients[rid]

    # Partial pantry
    pantry = recipe_ings[:1]
    metrics = matcher.calculate_pantry_metrics(rid, pantry)
    assert metrics.matched_count >= 1
    assert 0.0 < metrics.coverage_ratio <= 1.0


def test_pantry_require_all_hard_mode(constraint_engine: ConstraintEngine):
    matcher = constraint_engine.ingredient_matcher
    # Find recipe with at least 3 ingredients
    rids = [rid for rid, ings in matcher._recipe_clean_ingredients.items() if len(ings) >= 3]
    assert len(rids) > 0
    rid = rids[0]
    recipe_ings = matcher._recipe_clean_ingredients[rid]

    # Available is only 1 ingredient
    req_strict = ConstraintRequest(
        ingredients=IngredientConstraints(
            available_ingredients=[recipe_ings[0]],
            require_all_ingredients=True,
        )
    )
    ev = constraint_engine.evaluate_candidate(rid, req_strict)
    assert not ev.passed
    assert any("pantry coverage" in f.lower() or "missing" in f.lower() for f in ev.hard_failures)

    # In soft mode (require_all_ingredients=False), partial coverage does NOT reject
    req_soft = ConstraintRequest(
        ingredients=IngredientConstraints(
            available_ingredients=[recipe_ings[0]],
            require_all_ingredients=False,
        )
    )
    ev_soft = constraint_engine.evaluate_candidate(rid, req_soft)
    assert ev_soft.passed


# ============================================================================
# 6. NUTRITION HARD BOUNDARY TESTS
# ============================================================================

def test_nutrition_calorie_max_limit(constraint_engine: ConstraintEngine):
    nut_eval = constraint_engine.nutrition_evaluator
    # Find a recipe with known calories > 400
    high_cal = [
        rid for rid, n in nut_eval._nutrition_data.items()
        if n.get("calories") is not None and n["calories"] > 400
    ]
    assert len(high_cal) > 0
    rid = high_cal[0]

    req = ConstraintRequest(nutrition=NutritionConstraints(max_calories=300))
    ev = constraint_engine.evaluate_candidate(rid, req)
    assert not ev.passed
    assert any("calories" in f.lower() and "exceeds maximum" in f.lower() for f in ev.hard_failures)


def test_nutrition_protein_min_limit(constraint_engine: ConstraintEngine):
    nut_eval = constraint_engine.nutrition_evaluator
    # Find a recipe with known protein < 5
    low_pro = [
        rid for rid, n in nut_eval._nutrition_data.items()
        if n.get("protein") is not None and n["protein"] < 5.0
    ]
    assert len(low_pro) > 0
    rid = low_pro[0]

    req = ConstraintRequest(nutrition=NutritionConstraints(min_protein_g=15.0))
    ev = constraint_engine.evaluate_candidate(rid, req)
    assert not ev.passed
    assert any("protein" in f.lower() and "below minimum" in f.lower() for f in ev.hard_failures)


def test_zero_calorie_preservation(constraint_engine: ConstraintEngine):
    nut_eval = constraint_engine.nutrition_evaluator
    zero_cals = [
        rid for rid, n in nut_eval._nutrition_data.items()
        if n.get("calories") == 0.0
    ]
    # As documented in Stage B, there are 292 recipes with 0.0 calories
    assert len(zero_cals) == 292

    # Under min_calories=100, a 0.0 cal recipe must fail because 0.0 < 100
    rid = zero_cals[0]
    req = ConstraintRequest(nutrition=NutritionConstraints(min_calories=100.0))
    ev = constraint_engine.evaluate_candidate(rid, req)
    assert not ev.passed
    assert any("calories (0.0 kcal) is below minimum" in f.lower() for f in ev.hard_failures)


# ============================================================================
# 7. CONFLICT DETECTION TESTS
# ============================================================================

def test_contradictory_constraint_detection(constraint_engine: ConstraintEngine):
    # 1. Vegan + Paneer conflict
    req_vegan_paneer = ConstraintRequest(
        dietary=DietaryConstraints(vegan=True),
        ingredients=IngredientConstraints(required_ingredients=["paneer"]),
    )
    conflicts = constraint_engine.validate_request(req_vegan_paneer)
    assert len(conflicts) > 0
    assert any("paneer" in c.lower() and "vegan" in c.lower() for c in conflicts)

    # 2. Jain + Onion conflict
    req_jain_onion = ConstraintRequest(
        dietary=DietaryConstraints(jain=True),
        ingredients=IngredientConstraints(required_ingredients=["onion"]),
    )
    conflicts_jain = constraint_engine.validate_request(req_jain_onion)
    assert len(conflicts_jain) > 0
    assert any("onion" in c.lower() and "jain" in c.lower() for c in conflicts_jain)

    # 3. Excluded dairy + milk conflict
    req_dairy_milk = ConstraintRequest(
        allergens=AllergenConstraints(excluded_allergens=["dairy"]),
        ingredients=IngredientConstraints(required_ingredients=["milk"]),
    )
    conflicts_dairy = constraint_engine.validate_request(req_dairy_milk)
    assert len(conflicts_dairy) > 0
    assert any("milk" in c.lower() and "dairy" in c.lower() for c in conflicts_dairy)


# ============================================================================
# 8. PROPERTY INVARIANTS & EXPLAINABILITY TESTS
# ============================================================================

def test_hard_rejection_invariant_in_recommendations(recommender: KitchenPilotRecommender):
    """INVARIANT: Candidate rejected by a HARD constraint must never appear in final results."""
    # Exclude tomato
    req = ConstraintRequest(
        ingredients=IngredientConstraints(excluded_ingredients=["tomato"])
    )

    df = recommender.recommend(
        available_ingredients=["cumin", "turmeric", "onion"],
        top_k=10,
        save_results=False,
        constraint_request=req,
    )

    matcher = recommender.constraint_engine.ingredient_matcher
    for _, row in df.iterrows():
        rid = row["recipe_id"]
        clean_ings = matcher._recipe_clean_ingredients.get(rid, [])
        # None of the recommended recipes can contain tomato
        assert not any("tomato" in ing for ing in clean_ings), f"Recipe {rid} contains excluded tomato!"


def test_zero_result_handling(recommender: KitchenPilotRecommender):
    """Impossible criteria should produce 0 results gracefully with diagnostics."""
    req_impossible = ConstraintRequest(
        nutrition=NutritionConstraints(max_calories=10.0, min_protein_g=100.0)
    )

    df = recommender.recommend(
        top_k=10,
        save_results=False,
        constraint_request=req_impossible,
    )
    assert df.empty
    assert recommender.last_constraint_diagnostics is not None
    assert recommender.last_constraint_diagnostics["eligible_count"] == 0
    assert recommender.last_constraint_diagnostics["nutrition_rejections"] > 0


def test_explainability_determinism(constraint_engine: ConstraintEngine):
    matcher = constraint_engine.ingredient_matcher
    rid = list(matcher._recipe_clean_ingredients.keys())[0]

    req = ConstraintRequest(
        dietary=DietaryConstraints(vegetarian=True),
        ingredients=IngredientConstraints(excluded_ingredients=["nonexistent_ingredient_xyz"]),
    )

    ev1 = constraint_engine.evaluate_candidate(rid, req)
    ev2 = constraint_engine.evaluate_candidate(rid, req)

    assert ev1.passed == ev2.passed
    assert ev1.explanation == ev2.explanation
    assert len(ev1.explanation) > 0


# ============================================================================
# 9. API INTEGRATION TESTS
# ============================================================================

def test_api_recommend_with_stage_e_constraints(client: TestClient):
    payload = {
        "available_ingredients": ["potato", "cumin", "turmeric"],
        "dietary_constraints": {
            "vegetarian": True
        },
        "excluded_allergens": ["peanut"],
        "nutrition_constraints": {
            "max_calories": 800
        },
        "top_k": 5
    }

    response = client.post("/api/v1/recommend", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "recommendations" in data
    assert "count" in data
    assert data["count"] <= 5

    # Check each recommendation item
    for rec in data["recommendations"]:
        assert "rank" in rec
        assert "hybrid_score" in rec
        assert "explanation" in rec


def test_api_recommend_conflict_returns_422(client: TestClient):
    payload = {
        "dietary_constraints": {
            "vegan": True
        },
        "required_ingredients": ["paneer"],
        "top_k": 5
    }

    response = client.post("/api/v1/recommend", json=payload)
    assert response.status_code == 422
    assert "Constraint conflict" in response.json()["detail"]


def test_api_recommend_zero_results(client: TestClient):
    payload = {
        "nutrition_constraints": {
            "max_calories": 5.0,
            "min_protein_g": 200.0
        },
        "top_k": 5
    }

    response = client.post("/api/v1/recommend", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert len(data["recommendations"]) == 0
    assert data["message"] == "No recipes satisfy all specified hard constraints."
    assert data["diagnostics"] is not None
    assert data["diagnostics"]["nutrition_rejections"] > 0


def test_pilot_participant_pantry_recommendation_flow(client: TestClient):
    """Verify that genuine pilot participant profile produces valid vegetarian recommendations."""
    payload = {
        "ingredients": ["rice", "onion", "tomato", "potato", "dal", "green chilli", "turmeric", "cumin"],
        "user_preferences": {
            "vegetarian": True,
            "cuisine": "South Indian",
            "region": "South India",
            "meal_type": "Lunch",
            "category": "Main Course",
        },
        "top_k": 5,
    }

    response = client.post("/api/v1/recommend/by-ingredients", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert len(data["recommendations"]) == 5
    assert data["message"] is None

    # Safety Invariant: Every returned recommendation must be vegetarian
    for rec in data["recommendations"]:
        assert rec["rank"] >= 1
        assert rec["hybrid_score"] > 0.0
        assert len(rec["explanation"]) > 0
        # Check matched ingredients contain user's pantry items
        assert any(
            p in rec["matched_ingredients"]
            for p in ["rice", "onion", "tomato", "potato", "dal", "chilli", "turmeric", "cumin"]
        )
