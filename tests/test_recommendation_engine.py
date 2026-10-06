"""Unit and Integration Tests for KitchenPilot-V1 Recommendation Engine.

Tests:
1. TF-IDF artifact persistence and shapes
2. Determinism of recommendations
3. Self-exclusion of query recipe
4. Boundedness of all score components in [0, 1]
5. Strict monotonic ranking order
6. Hard dietary filters (vegetarian, vegan)
7. Excluded ingredients strict avoidance
8. Required ingredients strict inclusion
9. Empty ingredient resilience
10. Unknown ingredient resilience
11. Nutrition-aware scoring and confidence
12. Top-k parameter handling
13. Explainability completeness
14. Offline metrics evaluator
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from src.recommendation import (
    KitchenPilotRecommender,
    NutritionGoals,
    RecommendationConfig,
    UserPreferences,
)
from src.evaluation import RecommendationMetricsEvaluator

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def recommender():
    config = RecommendationConfig()
    return KitchenPilotRecommender(config)


def test_tfidf_artifacts_exist(recommender):
    """Verify that TF-IDF model artifacts are generated and indexed correctly."""
    assert recommender.config.tfidf_vectorizer_path.is_file()
    assert recommender.config.tfidf_matrix_path.is_file()
    assert recommender.config.recipe_index_path.is_file()
    assert len(recommender.tfidf_model.recipe_ids) == 6871
    assert recommender.tfidf_model.tfidf_matrix.shape[0] == 6871
    assert recommender.tfidf_model.tfidf_matrix.shape[1] > 10000


def test_deterministic_recommendations(recommender):
    """Verify that identical inputs produce bit-exact identical recommendations."""
    r1 = recommender.recommend(query_recipe_id="R00001", top_k=5, save_results=False)
    r2 = recommender.recommend(query_recipe_id="R00001", top_k=5, save_results=False)
    assert list(r1["recipe_id"]) == list(r2["recipe_id"])
    assert np.allclose(r1["hybrid_score"], r2["hybrid_score"])


def test_input_recipe_self_exclusion(recommender):
    """Verify that Mode A never recommends the input query recipe to the user."""
    recs = recommender.recommend(query_recipe_id="R00006", top_k=10, save_results=False)
    assert "R00006" not in recs["recipe_id"].values


def test_score_bounds_and_validity(recommender):
    """Verify that all score columns are strictly in [0.0, 1.0] and contain no NaNs/infs."""
    recs = recommender.recommend(
        available_ingredients=["rice", "tomato", "onion"],
        nutrition_goals=NutritionGoals(calorie_target=400.0),
        top_k=10,
        save_results=False,
    )
    score_cols = ["hybrid_score", "similarity_score", "ingredient_match_score", "nutrition_score", "preference_score"]
    for col in score_cols:
        vals = recs[col].values
        assert not np.isnan(vals).any(), f"Found NaN in {col}"
        assert not np.isinf(vals).any(), f"Found inf in {col}"
        assert np.all((vals >= 0.0) & (vals <= 1.0)), f"Values out of bounds in {col}"


def test_ranking_monotonicity(recommender):
    """Verify that results are sorted in descending order of hybrid_score."""
    recs = recommender.recommend(query_recipe_id="R00029", top_k=10, save_results=False)
    scores = recs["hybrid_score"].values
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1] - 1e-6, "Ranking is not monotonically non-increasing"


def test_hard_filter_vegetarian(recommender):
    """Verify that vegetarian=True excludes all non-vegetarian recipes."""
    recs = recommender.recommend(
        user_preferences=UserPreferences(vegetarian=True),
        top_k=25,
        save_results=False,
    )
    meta = recommender.preference_filter._recipes_metadata
    for rid in recs["recipe_id"]:
        assert meta[rid]["vegetarian"] is True, f"Non-vegetarian recipe recommended: {rid}"


def test_hard_filter_vegan(recommender):
    """Verify that vegan=True excludes all non-vegan recipes."""
    recs = recommender.recommend(
        user_preferences=UserPreferences(vegan=True),
        top_k=10,
        save_results=False,
    )
    meta = recommender.preference_filter._recipes_metadata
    for rid in recs["recipe_id"]:
        is_vegan = meta[rid]["vegan"] or ("vegan" in meta[rid]["diet_type"]) or ("vegan" in meta[rid]["recipe_name"].lower())
        assert is_vegan, f"Non-vegan recipe recommended: {rid}"


def test_excluded_ingredients_enforcement(recommender):
    """Verify that excluded ingredients never appear in recommendations."""
    recs = recommender.recommend(
        available_ingredients=["potato", "tomato", "onion"],
        user_preferences=UserPreferences(excluded_ingredients=["chicken", "fish", "egg"]),
        top_k=20,
        save_results=False,
    )
    for rid in recs["recipe_id"]:
        canons = recommender.ingredient_matcher._recipe_canonical_map.get(rid, set())
        all_ings = recommender.ingredient_matcher._recipe_all_ingredients.get(rid, [])
        for excluded in ["chicken", "fish", "egg"]:
            assert excluded not in canons, f"Excluded ingredient {excluded} found in {rid}"
            assert not any(excluded in i for i in all_ings), f"Excluded text {excluded} found in {rid}"


def test_required_ingredients_enforcement(recommender):
    """Verify that required ingredients are strictly included in all returned recipes."""
    recs = recommender.recommend(
        user_preferences=UserPreferences(required_ingredients=["paneer"]),
        top_k=10,
        save_results=False,
    )
    for rid in recs["recipe_id"]:
        canons = recommender.ingredient_matcher._recipe_canonical_map.get(rid, set())
        assert "paneer" in canons, f"Required ingredient 'paneer' missing in {rid}"


def test_empty_ingredient_list_safety(recommender):
    """Verify safe execution when ingredient list is empty."""
    recs = recommender.recommend(available_ingredients=[], top_k=5, save_results=False)
    assert len(recs) == 5
    assert not recs["hybrid_score"].isna().any()


def test_unknown_ingredient_safety(recommender):
    """Verify resilience when user inputs non-existent or unknown ingredient strings."""
    recs = recommender.recommend(
        available_ingredients=["completely_unknown_ingredient_xyz_123"],
        top_k=5,
        save_results=False,
    )
    assert len(recs) == 5
    assert not recs["hybrid_score"].isna().any()


def test_nutrition_scoring_and_confidence(recommender):
    """Verify that nutrition scoring favors recipes aligning with calorie targets and sets confidence."""
    goals = NutritionGoals(calorie_target=300.0, max_calories=400.0)
    recs = recommender.recommend(nutrition_goals=goals, top_k=10, save_results=False)
    assert len(recs) == 10
    for _, row in recs.iterrows():
        assert 0.0 <= row["nutrition_score"] <= 1.0
        assert 0.0 <= row["nutrition_confidence"] <= 1.0


def test_top_k_parameter_handling(recommender):
    """Verify that recommender respects different top_k values."""
    assert len(recommender.recommend(query_recipe_id="R00001", top_k=3, save_results=False)) == 3
    assert len(recommender.recommend(query_recipe_id="R00001", top_k=7, save_results=False)) == 7
    assert len(recommender.recommend(query_recipe_id="R00001", top_k=12, save_results=False)) == 12


def test_explainability_clauses_present(recommender):
    """Verify that natural language explanations are present and descriptive."""
    recs = recommender.recommend(
        query_recipe_id="R00002",
        available_ingredients=["rice", "tomato", "chilli"],
        nutrition_goals=NutritionGoals(calorie_target=350.0),
        top_k=5,
        save_results=False,
    )
    for _, row in recs.iterrows():
        expl = row["explanation"]
        assert expl.startswith("Recommended because it ")
        assert len(expl) > 25


def test_offline_evaluation_suite(recommender):
    """Verify that the offline evaluation metrics module executes properly."""
    evaluator = RecommendationMetricsEvaluator(recommender)
    metrics = evaluator.evaluate(top_k=5)

    assert metrics["precision_at_k"] == "Ground truth unavailable"
    assert metrics["recall_at_k"] == "Ground truth unavailable"
    assert 0.0 < metrics["catalog_coverage"] <= 1.0
    assert 0.0 <= metrics["average_intra_list_diversity"] <= 1.0
    assert metrics["average_response_time_ms"] > 0.0
    assert metrics["is_deterministic"] is True


def test_bitter_gourd_disliked_soft_penalty(recommender):
    """Verify that disliked bitter gourd is detected in recipes like R10498 and causes a soft penalty."""
    # Test matcher directly on R10498
    matcher = recommender.ingredient_matcher
    res_disliked = matcher.match_recipe("R10498", disliked_ingredients=["bitter gourd"])
    res_normal = matcher.match_recipe("R10498", disliked_ingredients=[])

    assert "bitter gourd" in res_disliked.disliked_found
    assert res_disliked.match_score < res_normal.match_score
    assert pytest.approx(res_disliked.match_score, 0.01) == 0.8
    assert pytest.approx(res_normal.match_score, 0.01) == 1.0

    # Also test via aliases
    res_karela = matcher.match_recipe("R10498", disliked_ingredients=["karela"])
    assert "bitter gourd" in res_karela.disliked_found
    assert pytest.approx(res_karela.match_score, 0.01) == 0.8

    res_pavakkai = matcher.match_recipe("R10498", disliked_ingredients=["pavakkai"])
    assert "bitter gourd" in res_pavakkai.disliked_found
    assert pytest.approx(res_pavakkai.match_score, 0.01) == 0.8

    # Verify bitter-gourd recipes are not hard-filtered when disliked
    prefs_dislike = UserPreferences(disliked_ingredients=["bitter gourd"])
    recs = recommender.recommend(
        query_recipe_id="R10498",
        user_preferences=prefs_dislike,
        top_k=5,
        save_results=False,
    )
    assert len(recs) == 5
