"""Dedicated Regression Test Suite for Satvik and Dietary Compliance Filtering.

Validates the 11 critical dietary filtering requirements:
1. R00014 is rejected for Satvik recommendations.
2. A fish ingredient is detected when its canonical mapping is missing.
3. A recipe with satvik=True but containing fish is rejected.
4. A recipe with vegetarian=True but containing fish is rejected for vegetarian and Satvik requests.
5. Chicken and other recognized non-vegetarian ingredients are rejected under strict dietary constraints.
6. Onion and garlic remain prohibited under Satvik rules.
7. A valid vegetarian/Satvik recipe without prohibited ingredients passes when available data is sufficient.
8. Unknown or insufficient ingredient data fails closed (UNKNOWN) under strict constraints.
9. Both constraint-engine and legacy recommendation paths enforce dietary restrictions identically.
10. Semantic recommendations cannot bypass dietary and Indian-cuisine eligibility rules.
11. Recommendation explanations and API response labels do not claim compliance for rejected recipes.
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
    IngredientConstraints,
)
from src.constraints.dietary import DietaryRuleEngine, detect_prohibited_non_veg
from src.recommendation.ingredient_matcher import IngredientMatcher
from src.recommendation.preference_filter import PreferenceFilter, UserPreferences
from src.recommendation.recommender import KitchenPilotRecommender


@pytest.fixture(scope="module")
def constraint_engine() -> ConstraintEngine:
    return ConstraintEngine()


@pytest.fixture(scope="module")
def dietary_engine() -> DietaryRuleEngine:
    return DietaryRuleEngine()


@pytest.fixture(scope="module")
def recommender() -> KitchenPilotRecommender:
    return KitchenPilotRecommender()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


# ============================================================================
# Requirement 1: R00014 rejected for Satvik recommendations
# ============================================================================
def test_r00014_rejected_for_satvik(constraint_engine: ConstraintEngine):
    """Verify R00014 (Bengali fish soup) is strictly rejected under Satvik constraints."""
    req = ConstraintRequest(dietary=DietaryConstraints(satvik=True))
    ev = constraint_engine.evaluate_candidate("R00014", req)

    assert not ev.passed, "R00014 must not pass Satvik constraint!"
    assert ev.dietary_results.get("satvik") == ComplianceStatus.NON_COMPLIANT
    assert len(ev.hard_failures) > 0
    assert any("non vegetarian" in f.lower() or "fish" in f.lower() or "maach" in f.lower() for f in ev.hard_failures)


# ============================================================================
# Requirement 2: Fish detected when canonical mapping is missing
# ============================================================================
def test_unmapped_fish_ingredient_detected_without_canonical_mapping(dietary_engine: DietaryRuleEngine):
    """Verify unmapped or raw ingredient phrases containing fish are detected."""
    unmapped_phrases = [
        "Aar Maach (fish)",
        "600 grams Aar Maach (fish) - rohu/ katla fish (cut into thick steaks)",
        "Basa fish fillet",
        "Pomfret fish sliced",
        "Rohu fish curry cut",
        "Hilsa fish steaks",
    ]
    for phrase in unmapped_phrases:
        detected = detect_prohibited_non_veg(phrase)
        assert detected is not None, f"Failed to detect fish in unmapped phrase: '{phrase}'"
        assert detected.lower() in ("fish", "maach", "rohu", "katla", "pomfret", "hilsa")


# ============================================================================
# Requirement 3: Recipe with satvik=True metadata containing fish is rejected
# ============================================================================
def test_recipe_with_satvik_true_containing_fish_is_rejected(dietary_engine: DietaryRuleEngine):
    """Verify that even if metadata explicitly claims satvik=True, fish ingredients cause rejection."""
    # Temporarily spoof metadata on an isolated recipe entry
    original_meta = dict(dietary_engine._recipes_metadata.get("R00014", {}))
    try:
        dietary_engine._recipes_metadata["R00014"]["satvik"] = True
        dietary_engine._recipes_metadata["R00014"]["vegetarian"] = True
        dietary_engine._recipes_metadata["R00014"]["diet_type"] = "sattvic"

        passed, failures, statuses = dietary_engine.evaluate_dietary_compliance(
            "R00014", DietaryConstraints(satvik=True)
        )
        assert not passed, "Recipe with satvik=True metadata containing fish must be rejected!"
        assert statuses.get("satvik") == ComplianceStatus.NON_COMPLIANT
        assert any("fish" in f.lower() or "maach" in f.lower() for f in failures)
    finally:
        dietary_engine._recipes_metadata["R00014"] = original_meta


# ============================================================================
# Requirement 4: Recipe with vegetarian=True metadata containing fish is rejected
# ============================================================================
def test_recipe_with_vegetarian_true_containing_fish_is_rejected(dietary_engine: DietaryRuleEngine):
    """Verify that a recipe with vegetarian=True in metadata containing fish is rejected for both veg and satvik."""
    original_meta = dict(dietary_engine._recipes_metadata.get("R00014", {}))
    try:
        # In current data/processed/recipes.csv, R00014 already has vegetarian=True!
        dietary_engine._recipes_metadata["R00014"]["vegetarian"] = True

        # Test Vegetarian request
        v_passed, v_fails, v_statuses = dietary_engine.evaluate_dietary_compliance(
            "R00014", DietaryConstraints(vegetarian=True)
        )
        assert not v_passed, "R00014 must be rejected under vegetarian constraint!"
        assert v_statuses.get("vegetarian") == ComplianceStatus.NON_COMPLIANT

        # Test Satvik request
        s_passed, s_fails, s_statuses = dietary_engine.evaluate_dietary_compliance(
            "R00014", DietaryConstraints(satvik=True)
        )
        assert not s_passed, "R00014 must be rejected under Satvik constraint!"
        assert s_statuses.get("satvik") == ComplianceStatus.NON_COMPLIANT
    finally:
        dietary_engine._recipes_metadata["R00014"] = original_meta


# ============================================================================
# Requirement 5: Chicken and other non-veg ingredients rejected under strict constraints
# ============================================================================
def test_chicken_and_meat_prohibited_under_dietary_constraints(dietary_engine: DietaryRuleEngine):
    """Verify chicken, mutton, prawn, egg, pork, and beef are rejected under Vegetarian and Satvik."""
    test_terms = ["chicken", "mutton", "prawns", "shrimp", "boiled egg", "pork", "beef", "lamb"]
    for term in test_terms:
        detected = detect_prohibited_non_veg(term)
        assert detected is not None, f"Failed to detect non-veg term: '{term}'"

    # Verify vegetarian legitimate uses are NOT falsely rejected
    veg_terms = [
        "Small Brinjal (Baingan / Eggplant)",
        "Eggless Mayonnaise",
        "Flaxmeal Egg Replacer",
        "Tender coconut meat",
        "Meat masala",
        "Khaman dhokla",
        "Chamomile tea",
    ]
    for term in veg_terms:
        detected = detect_prohibited_non_veg(term)
        assert detected is None, f"False positive non-veg detection on legitimate vegetarian term: '{term}'"


# ============================================================================
# Requirement 6: Onion and garlic remain prohibited under Satvik rules
# ============================================================================
def test_onion_and_garlic_prohibited_under_satvik(constraint_engine: ConstraintEngine):
    """Verify recipes with onion or garlic are rejected under Satvik rules."""
    req = ConstraintRequest(dietary=DietaryConstraints(satvik=True))
    matcher = constraint_engine.ingredient_matcher
    meta = constraint_engine.dietary_engine._recipes_metadata

    # Select a vegetarian recipe containing onion or garlic
    garlic_recipes = [
        rid for rid, ings in matcher._recipe_clean_ingredients.items()
        if meta.get(rid, {}).get("vegetarian") is True and any("garlic" in i or "onion" in i for i in ings)
    ]
    assert len(garlic_recipes) > 0

    ev = constraint_engine.evaluate_candidate(garlic_recipes[0], req)
    assert not ev.passed
    assert ev.dietary_results.get("satvik") == ComplianceStatus.NON_COMPLIANT
    assert any("satvik" in f.lower() and ("garlic" in f.lower() or "onion" in f.lower()) for f in ev.hard_failures)


# ============================================================================
# Requirement 7: Valid vegetarian/Satvik recipe without prohibited items passes
# ============================================================================
def test_valid_satvik_recipe_passes_when_data_is_sufficient(constraint_engine: ConstraintEngine):
    """Verify that a genuine Sattvic recipe (e.g. R00122, R00143) passes compliance."""
    req = ConstraintRequest(dietary=DietaryConstraints(satvik=True))
    ev = constraint_engine.evaluate_candidate("R00122", req)

    assert ev.passed, f"Valid Sattvic recipe R00122 failed: {ev.hard_failures}"
    assert ev.dietary_results.get("satvik") == ComplianceStatus.COMPLIANT
    assert "satvik" in ev.explanation.lower() or "satisfies" in ev.explanation.lower()


# ============================================================================
# Requirement 8: Unknown or insufficient ingredient data fails closed
# ============================================================================
def test_insufficient_or_unknown_ingredient_data_fails_closed(dietary_engine: DietaryRuleEngine):
    """Verify recipes with zero ingredient data fail closed as UNKNOWN under strict constraints."""
    dietary_engine._recipes_metadata["R_NO_DATA"] = {
        "recipe_name": "Ghost Recipe",
        "diet_type": "sattvic",
        "vegetarian": True,
        "vegan": True,
        "jain": True,
        "satvik": True,
        "ingredients_text": "",
    }
    try:
        passed, failures, statuses = dietary_engine.evaluate_dietary_compliance(
            "R_NO_DATA", DietaryConstraints(satvik=True)
        )
        assert not passed, "Missing ingredient data must fail closed!"
        assert statuses.get("satvik") == ComplianceStatus.UNKNOWN
        assert any("insufficient ingredient data" in f.lower() for f in failures)
    finally:
        dietary_engine._recipes_metadata.pop("R_NO_DATA", None)


# ============================================================================
# Requirement 9: Both constraint-engine and legacy recommendation paths enforce rules
# ============================================================================
def test_both_constraint_engine_and_legacy_paths_enforce_dietary_rules():
    """Verify both constraint engine and PreferenceFilter reject R00014 and accept R00122."""
    ce = ConstraintEngine()
    pf = PreferenceFilter()
    im = IngredientMatcher()

    # Constraint engine path
    req_satvik = ConstraintRequest(dietary=DietaryConstraints(satvik=True))
    ev_r14 = ce.evaluate_candidate("R00014", req_satvik)
    ev_r122 = ce.evaluate_candidate("R00122", req_satvik)
    assert not ev_r14.passed
    assert ev_r122.passed

    # Legacy PreferenceFilter path
    pref_satvik = UserPreferences(satvik=True)
    assert not pf.passes_hard_filters("R00014", pref_satvik, im)
    assert pf.passes_hard_filters("R00122", pref_satvik, im)

    # Vegetarian check on both
    req_veg = ConstraintRequest(dietary=DietaryConstraints(vegetarian=True))
    assert not ce.evaluate_candidate("R00014", req_veg).passed
    pref_veg = UserPreferences(vegetarian=True)
    assert not pf.passes_hard_filters("R00014", pref_veg, im)


# ============================================================================
# Requirement 10: Semantic recommendations enforce dietary and Indian-cuisine rules
# ============================================================================
def test_semantic_recommendation_enforces_satvik_and_cuisine_rules(client: TestClient):
    """Verify semantic recommendation endpoint strictly rejects non-satvik recipes like fish soup."""
    payload = {
        "query": "fish soup Bengali style",
        "dietary_constraints": {
            "satvik": True
        },
        "top_k": 5
    }
    resp = client.post("/api/v1/recommend/semantic", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    recs = data.get("recommendations", [])

    # None of the returned recommendations can be R00014 or contain fish
    for item in recs:
        assert item["recipe_id"] != "R00014", "R00014 leaked through semantic Satvik recommendations!"
        assert "fish" not in item["recipe_name"].lower(), f"Fish recipe leaked: {item['recipe_name']}"


# ============================================================================
# Requirement 11: Explanations and API response labels do not claim compliance for rejected recipes
# ============================================================================
def test_explanations_and_api_responses_do_not_claim_compliance_for_rejected_recipes(constraint_engine: ConstraintEngine):
    """Verify constraint evaluation explanations for rejected recipes never state compliance."""
    req = ConstraintRequest(dietary=DietaryConstraints(satvik=True))
    ev = constraint_engine.evaluate_candidate("R00014", req)

    assert not ev.passed
    assert ev.explanation.startswith("Rejected:")
    assert "satisfies satvik" not in ev.explanation.lower()
    assert "eligible" not in ev.explanation.lower()


# ============================================================================
# Additional Independent Review Regressions: Title Negations & Safe Exclusions
# ============================================================================

def test_title_with_no_onion_no_garlic_passes_satvik(dietary_engine: DietaryRuleEngine):
    """Verify recipe title proclaiming 'No Onion No Garlic' does NOT trigger tamasic rejection."""
    dietary_engine._recipes_metadata["R_NO_ONION_TITLE"] = {
        "recipe_name": "Paneer Butter Masala (No Onion No Garlic)",
        "diet_type": "sattvic",
        "vegetarian": True,
        "vegan": False,
        "jain": False,
        "satvik": True,
        "ingredients_text": "paneer, tomato, butter, cumin, garam masala, salt",
    }
    try:
        passed, failures, statuses = dietary_engine.evaluate_dietary_compliance(
            "R_NO_ONION_TITLE", DietaryConstraints(satvik=True)
        )
        assert passed, f"Satvik title with negation failed: {failures}"
        assert statuses.get("satvik") == ComplianceStatus.COMPLIANT
    finally:
        dietary_engine._recipes_metadata.pop("R_NO_ONION_TITLE", None)


def test_title_with_jain_negation_passes_jain(dietary_engine: DietaryRuleEngine):
    """Verify recipe title proclaiming 'Jain Pav Bhaji (No Potato)' does NOT trigger Jain root rejection."""
    dietary_engine._recipes_metadata["R_JAIN_TITLE"] = {
        "recipe_name": "Jain Pav Bhaji (No Potato)",
        "diet_type": "jain",
        "vegetarian": True,
        "vegan": False,
        "jain": True,
        "satvik": False,
        "ingredients_text": "raw banana, green peas, tomato, butter, pav bhaji masala",
    }
    try:
        passed, failures, statuses = dietary_engine.evaluate_dietary_compliance(
            "R_JAIN_TITLE", DietaryConstraints(jain=True)
        )
        assert passed, f"Jain title with negation failed: {failures}"
        assert statuses.get("jain") == ComplianceStatus.COMPLIANT
    finally:
        dietary_engine._recipes_metadata.pop("R_JAIN_TITLE", None)


def test_title_with_mock_meat_or_soya_keema_passes_vegetarian(dietary_engine: DietaryRuleEngine):
    """Verify titles with mock meat or soya keema do NOT trigger non-vegetarian rejection."""
    dietary_engine._recipes_metadata["R_SOYA_KEEMA"] = {
        "recipe_name": "Soya Keema Matar Masala Recipe",
        "diet_type": "vegetarian",
        "vegetarian": True,
        "vegan": False,
        "jain": False,
        "satvik": False,
        "ingredients_text": "soya granules, green peas, onion, tomato, spices",
    }
    try:
        passed, failures, statuses = dietary_engine.evaluate_dietary_compliance(
            "R_SOYA_KEEMA", DietaryConstraints(vegetarian=True)
        )
        assert passed, f"Soya keema failed vegetarian check: {failures}"
        assert statuses.get("vegetarian") == ComplianceStatus.COMPLIANT
    finally:
        dietary_engine._recipes_metadata.pop("R_SOYA_KEEMA", None)


def test_eggplant_does_not_conflict_with_vegetarian_constraint(constraint_engine: ConstraintEngine):
    """Verify requiring 'eggplant' does not trigger false 'egg' conflict in validate_request."""
    req = ConstraintRequest(
        dietary=DietaryConstraints(vegetarian=True),
        ingredients=IngredientConstraints(required_ingredients=["eggplant"]),
    )
    conflicts = constraint_engine.validate_request(req)
    assert len(conflicts) == 0, f"Eggplant produced false conflict: {conflicts}"


def test_coconut_milk_does_not_conflict_with_vegan_or_dairy_allergen(constraint_engine: ConstraintEngine):
    """Verify requiring 'coconut milk' does not trigger vegan or dairy allergen conflicts."""
    req = ConstraintRequest(
        dietary=DietaryConstraints(vegan=True),
        allergens=AllergenConstraints(excluded_allergens=["dairy"]),
        ingredients=IngredientConstraints(required_ingredients=["coconut milk"]),
    )
    conflicts = constraint_engine.validate_request(req)
    assert len(conflicts) == 0, f"Coconut milk produced false conflict: {conflicts}"


def test_devanagari_egg_ingredient_detected_as_non_veg(dietary_engine: DietaryRuleEngine):
    """Verify Hindi / Devanagari non-veg terms (e.g. अंडे) are detected as non-vegetarian."""
    assert detect_prohibited_non_veg("2 अंडे (उबले हुए)") == "अंडे"
    assert detect_prohibited_non_veg("ताज़ा मछली") == "मछली"
    assert detect_prohibited_non_veg("चिकन टिक्का") == "चिकन"
