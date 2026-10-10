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
from src.data.cuisine_policy import is_indian_cuisine
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


def test_standard_recommendations_enforce_indian_only_and_handle_high_row_indices(recommender):
    """Verify standard recommendations return only approved Indian recipes and handle TF-IDF indices > 4724."""
    # Test Mode A with non-Indian seed recipe 'R00008'
    recs_a = recommender.recommend(query_recipe_id="R00008", top_k=10, save_results=False)
    assert len(recs_a) == 10
    assert "R00008" not in recs_a["recipe_id"].values
    for rid in recs_a["recipe_id"]:
        cuisine = recommender._recipe_metadata.get(rid, {}).get("cuisine")
        assert is_indian_cuisine(cuisine), f"Non-Indian recipe returned in Mode A: {rid} ({cuisine})"

    # Test Mode B with ingredients and dietary preferences
    recs_b = recommender.recommend(
        available_ingredients=["paneer", "onion", "tomato"],
        user_preferences=UserPreferences(vegetarian=True),
        top_k=10,
        save_results=False,
    )
    assert len(recs_b) == 10
    for rid in recs_b["recipe_id"]:
        cuisine = recommender._recipe_metadata.get(rid, {}).get("cuisine")
        assert is_indian_cuisine(cuisine), f"Non-Indian recipe returned in Mode B: {rid} ({cuisine})"

    # Test empty ingredients zero-similarity path (specifically testing candidates with row_idx > 4724)
    recs_empty = recommender.recommend(available_ingredients=[], top_k=20, save_results=False)
    assert len(recs_empty) == 20
    # Check that high row-index recipes exist in candidate pool and don't cause IndexError
    high_index_rids = [
        rid for rid in recommender.tfidf_model.recipe_ids
        if recommender.tfidf_model.recipe_to_row.get(rid, 0) >= 4724
        and is_indian_cuisine(recommender._recipe_metadata.get(rid, {}).get("cuisine"))
    ]
    assert len(high_index_rids) > 0, "Expected approved Indian recipes with original TF-IDF row index >= 4724"
    # Ensure recipe 4922 specifically exists in TF-IDF index
    recipe_4922 = recommender.tfidf_model.row_to_recipe.get(4922)
    assert recipe_4922 is not None


def test_semantic_recommendations_enforce_indian_only(recommender):
    """Verify semantic recommendations return only approved Indian recipes even for international queries."""
    # South Indian query
    recs_south = recommender.recommend_semantic(
        query="vegetarian South Indian breakfast with lentils",
        top_k=5,
        save_results=False,
    )
    assert len(recs_south) == 5
    for rid in recs_south["recipe_id"]:
        cuisine = recommender._recipe_metadata.get(rid, {}).get("cuisine")
        assert is_indian_cuisine(cuisine), f"Non-Indian recipe in semantic search: {rid} ({cuisine})"

    # International query (e.g. pasta) - ensure returned items are approved Indian dishes
    recs_pasta = recommender.recommend_semantic(
        query="spaghetti pasta bolognese",
        top_k=5,
        save_results=False,
    )
    assert len(recs_pasta) > 0
    for rid in recs_pasta["recipe_id"]:
        cuisine = recommender._recipe_metadata.get(rid, {}).get("cuisine")
        assert is_indian_cuisine(cuisine), f"Non-Indian recipe in pasta query: {rid} ({cuisine})"


def test_non_indian_and_missing_cuisine_metadata_strictly_excluded(recommender):
    """Verify that recipes with missing, empty, or unapproved cuisine metadata are never recommended."""
    # Known non-Indian recipes in corpus
    non_indian_sample = {"R00008", "R00011", "R00012", "R00019", "R00023"}
    for seed in ["R00001", "R00006"]:
        recs = recommender.recommend(query_recipe_id=seed, top_k=20, save_results=False)
        for rid in recs["recipe_id"]:
            assert rid not in non_indian_sample, f"Non-Indian recipe {rid} leaked into recommendations"
            meta = recommender._recipe_metadata.get(rid, {})
            assert is_indian_cuisine(meta.get("cuisine")), f"Recipe {rid} has unapproved cuisine: {meta.get('cuisine')}"

    # Verify that a recipe with empty or missing cuisine metadata is excluded
    dummy_rid = "MOCK_UNKNOWN_RID_99999"
    # Even if present in tfidf_model.recipe_ids, absence of approved metadata excludes it
    assert is_indian_cuisine(recommender._recipe_metadata.get(dummy_rid, {}).get("cuisine")) is False


def test_candidate_pool_recipe_with_missing_or_unapproved_metadata_cannot_be_recommended(recommender):
    """Verify that any recipe in the candidate pool with missing or unapproved cuisine metadata cannot be recommended."""
    # 1. Standard recommendation (Mode A): Take a top candidate and corrupt its metadata
    base_recs = recommender.recommend(query_recipe_id="R00001", top_k=5, save_results=False)
    assert len(base_recs) > 0
    target_rid = base_recs["recipe_id"].iloc[0]
    orig_meta = recommender._recipe_metadata[target_rid].copy()

    try:
        # A. Unapproved international cuisine
        recommender._recipe_metadata[target_rid]["cuisine"] = "Mexican"
        recs = recommender.recommend(query_recipe_id="R00001", top_k=5, save_results=False)
        assert target_rid not in recs["recipe_id"].values

        # B. None cuisine
        recommender._recipe_metadata[target_rid]["cuisine"] = None
        recs = recommender.recommend(query_recipe_id="R00001", top_k=5, save_results=False)
        assert target_rid not in recs["recipe_id"].values

        # C. Empty string cuisine
        recommender._recipe_metadata[target_rid]["cuisine"] = ""
        recs = recommender.recommend(query_recipe_id="R00001", top_k=5, save_results=False)
        assert target_rid not in recs["recipe_id"].values

        # D. Completely missing metadata entry
        del recommender._recipe_metadata[target_rid]
        recs = recommender.recommend(query_recipe_id="R00001", top_k=5, save_results=False)
        assert target_rid not in recs["recipe_id"].values
    finally:
        recommender._recipe_metadata[target_rid] = orig_meta

    # 2. Semantic retrieval candidate pool injection:
    # Directly inject candidate with unapproved and missing cuisine into retriever output
    from src.retrieval.base import RetrievalResult

    real_retrieve = recommender.semantic_retriever.retrieve

    unapproved_id = "MOCK_UNAPPROVED_CANDIDATE"
    missing_id = "MOCK_MISSING_CANDIDATE"
    recommender._recipe_metadata[unapproved_id] = {
        "recipe_name": "Unapproved Burrito",
        "cuisine": "Mexican",
        "vegetarian": True,
        "vegan": False,
        "jain": False,
        "satvik": False,
    }
    # missing_id is intentionally not in _recipe_metadata at all

    def mock_retrieve_with_injected(query, top_k):
        raw = real_retrieve(query, top_k)
        # Inject at the very top with 1.0 similarity score
        return [
            RetrievalResult(unapproved_id, 1.0, 1, "semantic"),
            RetrievalResult(missing_id, 0.99, 2, "semantic"),
        ] + list(raw)

    try:
        recommender.semantic_retriever.retrieve = mock_retrieve_with_injected
        sem_recs = recommender.recommend_semantic(query="paneer tikka", top_k=5, save_results=False)
        assert unapproved_id not in sem_recs["recipe_id"].values
        assert missing_id not in sem_recs["recipe_id"].values
        for r_id in sem_recs["recipe_id"]:
            cuisine = recommender._recipe_metadata.get(r_id, {}).get("cuisine")
            assert is_indian_cuisine(cuisine)
    finally:
        recommender.semantic_retriever.retrieve = real_retrieve
        recommender._recipe_metadata.pop(unapproved_id, None)


def test_semantic_recommendations_bounded_retrieval_and_candidate_limit(recommender):
    """Verify semantic retrieval retrieves candidates in bounded batches without full-corpus scan when possible."""
    real_retrieve = recommender.semantic_retriever.retrieve
    call_log = []

    def mock_retrieve(query, top_k):
        call_log.append(top_k)
        return real_retrieve(query, top_k)

    try:
        recommender.semantic_retriever.retrieve = mock_retrieve
        recs = recommender.recommend_semantic(
            query="South Indian sambar and idli",
            top_k=5,
            candidate_k=20,
            save_results=False,
        )
        assert len(recs) == 5
        # Total corpus has thousands of recipes (e.g. 6871)
        total_corpus = len(recommender.semantic_retriever.recipe_ids)
        assert total_corpus > 1000

        # Initial call should be bounded: min(total_corpus, max(20 * 2, 100)) = 100
        assert len(call_log) == 1
        assert call_log[0] == 100
        assert call_log[0] < total_corpus

        for rid in recs["recipe_id"]:
            assert is_indian_cuisine(recommender._recipe_metadata.get(rid, {}).get("cuisine"))
    finally:
        recommender.semantic_retriever.retrieve = real_retrieve


def test_semantic_recommendations_fallback_expansion(recommender):
    """Verify fallback expansion triggers when initial bounded batch yields insufficient approved recipes."""
    from src.retrieval.base import RetrievalResult

    real_retrieve = recommender.semantic_retriever.retrieve
    call_log = []

    # Get real Indian recipe IDs
    indian_ids = [
        rid for rid in recommender.semantic_retriever.recipe_ids
        if is_indian_cuisine(recommender._recipe_metadata.get(rid, {}).get("cuisine"))
    ][:10]

    def mock_retrieve(query, top_k):
        call_log.append(top_k)
        if len(call_log) == 1:
            # First bounded call: return mostly non-Indian results and only 1 Indian result
            fake_results = [
                RetrievalResult(f"NON_INDIAN_{i}", 0.95 - (i * 0.001), i + 1, "semantic")
                for i in range(top_k - 1)
            ]
            fake_results.append(RetrievalResult(indian_ids[0], 0.96, top_k, "semantic"))
            # Set metadata for fake non-Indian
            for f in fake_results[:-1]:
                recommender._recipe_metadata[f.recipe_id] = {"cuisine": "Continental", "vegetarian": True}
            return fake_results
        else:
            # Fallback expanded call: return full corpus with real retriever
            return real_retrieve(query, top_k)

    try:
        recommender.semantic_retriever.retrieve = mock_retrieve
        recs = recommender.recommend_semantic(
            query="traditional breakfast",
            top_k=5,
            candidate_k=5,
            save_results=False,
        )
        # Should have called retrieve twice: first bounded, then fallback expanded
        assert len(call_log) == 2
        assert call_log[0] == 100
        assert call_log[1] == len(recommender.semantic_retriever.recipe_ids)

        assert len(recs) == 5
        for rid in recs["recipe_id"]:
            assert is_indian_cuisine(recommender._recipe_metadata.get(rid, {}).get("cuisine"))
            assert not rid.startswith("NON_INDIAN_")
    finally:
        recommender.semantic_retriever.retrieve = real_retrieve
        # Clean up any temporary fake metadata
        for k in list(recommender._recipe_metadata.keys()):
            if k.startswith("NON_INDIAN_"):
                del recommender._recipe_metadata[k]
