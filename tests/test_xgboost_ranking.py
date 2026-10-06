"""Comprehensive Test Suite for Stage F XGBoost Learning-to-Rank Engine.

Validates:
1. Feature generation (dimension, ordering, determinism, finite values, missing value handling)
2. Ranking dataset schema and group-level train/val/test isolation (zero query leakage)
3. XGBoost model loading, metadata integrity, and prediction stability
4. Deterministic multi-tier tie-breaking
5. Strict hard constraint preservation (invariants: 0 violations, hard filters before ranking)
6. Fallback resilience (disabled flag, missing model, corrupted model fallback to HybridRanker)
7. End-to-end integration with KitchenPilotRecommender
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
import pytest

from src.constraints import (
    ConstraintEngine,
    ConstraintRequest,
    DietaryConstraints,
    IngredientConstraints,
    NutritionConstraints,
)
from src.ranking import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    FeatureExtractor,
    RankingContext,
    RankingDatasetBuilder,
    RankingDispatcher,
    XGBoostRanker,
    compute_weak_relevance_label,
)
from src.recommendation.config import RecommendationConfig
from src.recommendation.hybrid_ranker import HybridRanker, ScoredCandidate
from src.recommendation.recommender import KitchenPilotRecommender

MODEL_PATH = Path("models/ranking/xgboost_ranker.json")
SCHEMA_PATH = Path("models/ranking/feature_schema.json")
METADATA_PATH = Path("models/ranking/metadata.json")


@pytest.fixture(scope="module")
def extractor() -> FeatureExtractor:
    return FeatureExtractor()


@pytest.fixture(scope="module")
def ranker(extractor: FeatureExtractor) -> XGBoostRanker:
    ranker = XGBoostRanker(
        model_path=MODEL_PATH,
        schema_path=SCHEMA_PATH,
        metadata_path=METADATA_PATH,
        feature_extractor=extractor,
    )
    ranker.load_model()
    return ranker


@pytest.fixture(scope="module")
def recommender() -> KitchenPilotRecommender:
    return KitchenPilotRecommender()


# ============================================================================
# 1. FEATURE GENERATION TESTS
# ============================================================================

def test_feature_extractor_schema_and_dimensions(extractor: FeatureExtractor):
    """Test feature extractor generates exact schema dimensions and order."""
    assert len(extractor.feature_names) == 30
    assert extractor.feature_names == FEATURE_NAMES
    assert extractor.feature_schema_version == FEATURE_SCHEMA_VERSION

    # Extract features for sample candidates
    context = RankingContext(
        available_ingredients=["paneer", "spinach"],
        calorie_target=500.0,
        tfidf_candidates={"RECIPE_0001": 0.75},
        bge_candidates={"RECIPE_0001": 0.82},
        tfidf_ranks={"RECIPE_0001": 0},
        bge_ranks={"RECIPE_0001": 0},
    )

    f_dict = extractor.extract_features_single("RECIPE_0001", context)
    assert len(f_dict) == 30
    for name in FEATURE_NAMES:
        assert name in f_dict
        val = f_dict[name]
        assert isinstance(val, (int, float))
        assert np.isfinite(val), f"Feature {name} has non-finite value {val}"

    # Matrix extraction
    mat, rows = extractor.extract_features(["RECIPE_0001"], context)
    assert mat.shape == (1, 30)
    assert len(rows) == 1


def test_feature_extractor_determinism(extractor: FeatureExtractor):
    """INVARIANT: Extracting features for the same candidate and context is strictly deterministic."""
    context = RankingContext(
        available_ingredients=["cumin", "turmeric"],
        tfidf_candidates={"RECIPE_0010": 0.45},
    )
    f1 = extractor.extract_features_single("RECIPE_0010", context)
    f2 = extractor.extract_features_single("RECIPE_0010", context)
    assert f1 == f2


def test_feature_extractor_missing_values_safe(extractor: FeatureExtractor):
    """Test feature extractor handles unknown/missing recipe IDs safely without exceptions."""
    context = RankingContext()
    f_unknown = extractor.extract_features_single("NON_EXISTENT_RECIPE_9999", context)
    assert len(f_unknown) == 30
    for k, v in f_unknown.items():
        assert np.isfinite(v)
    assert f_unknown["nutrition_available"] == 0.0
    assert f_unknown["hard_constraint_violation"] == 0.0


# ============================================================================
# 2. DATASET BUILDER & GROUP ISOLATION TESTS
# ============================================================================

def test_weak_relevance_label_logic():
    """Test multi-signal weak relevance labels obey safety rules."""
    # Dietary non-compliant must always be label 0
    assert compute_weak_relevance_label(0.9, 0.9, True, 1.0, dietary_compliant=False, nutrition_available=True) == 0

    # High agreement -> label 3
    assert compute_weak_relevance_label(0.6, 0.6, True, 0.8, dietary_compliant=True, nutrition_available=True) == 3

    # Moderate agreement -> label 2
    assert compute_weak_relevance_label(0.4, 0.2, False, 0.4, dietary_compliant=True, nutrition_available=True) == 2

    # Marginal -> label 1
    assert compute_weak_relevance_label(0.2, 0.1, False, 0.1, dietary_compliant=True, nutrition_available=True) == 1

    # Irrelevant -> label 0
    assert compute_weak_relevance_label(0.05, 0.05, False, 0.05, dietary_compliant=True, nutrition_available=False) == 0


def test_dataset_split_zero_query_leakage(extractor: FeatureExtractor):
    """INVARIANT: Group split guarantees zero query_id overlap between train, val, and test."""
    builder = RankingDatasetBuilder(feature_extractor=extractor)
    df_sample = pd.DataFrame([
        {"query_id": f"q_{i}", "recipe_id": f"r_{j}", "label": 1, **{f: 0.0 for f in FEATURE_NAMES}}
        for i in range(20) for j in range(5)
    ])

    df_train, df_val, df_test = builder.split_by_query_group(df_sample, 0.7, 0.15, 0.15, random_seed=42)

    train_q = set(df_train["query_id"])
    val_q = set(df_val["query_id"])
    test_q = set(df_test["query_id"])

    assert len(train_q & val_q) == 0
    assert len(train_q & test_q) == 0
    assert len(val_q & test_q) == 0
    assert len(train_q | val_q | test_q) == 20


# ============================================================================
# 3. XGBOOST MODEL LOADING & PREDICTION TESTS
# ============================================================================

def test_xgboost_model_artifact_and_metadata(ranker: XGBoostRanker):
    """Verify model loads, schema matches, and metadata is populated."""
    assert ranker.is_loaded
    assert ranker._model is not None
    assert len(ranker._feature_names) == 30

    assert METADATA_PATH.is_file()
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["model_name"] == "xgboost_ranker"
    assert meta["objective"] == "rank:ndcg"
    assert "evaluation_metrics" in meta
    assert "ndcg@5" in meta["evaluation_metrics"]


def test_xgboost_ranker_predictions_and_order(ranker: XGBoostRanker):
    """Test ranker returns finite scores and preserves candidate IDs."""
    candidates = ["RECIPE_0001", "RECIPE_0002", "RECIPE_0003"]
    context = RankingContext(
        available_ingredients=["potato", "cumin"],
        tfidf_candidates={"RECIPE_0001": 0.8, "RECIPE_0002": 0.4, "RECIPE_0003": 0.1},
        bge_candidates={"RECIPE_0001": 0.85, "RECIPE_0002": 0.3, "RECIPE_0003": 0.05},
    )

    ranked = ranker.rank(candidates, context, top_k=3)
    assert len(ranked) == 3
    for rid, score in ranked:
        assert rid in candidates
        assert np.isfinite(score)


def test_deterministic_tie_breaking(ranker: XGBoostRanker):
    """INVARIANT: Same candidates and context produce identical ranking order."""
    candidates = ["RECIPE_0005", "RECIPE_0006", "RECIPE_0007"]
    context = RankingContext(
        available_ingredients=["rice", "dal"],
        tfidf_candidates={"RECIPE_0005": 0.5, "RECIPE_0006": 0.5, "RECIPE_0007": 0.5},
    )

    r1 = ranker.rank(candidates, context, top_k=3)
    r2 = ranker.rank(candidates, context, top_k=3)
    assert r1 == r2


# ============================================================================
# 4. HARD CONSTRAINT SAFETY INVARIANT TESTS
# ============================================================================

def test_hard_constraints_strictly_enforced_before_xgboost(recommender: KitchenPilotRecommender):
    """CRITICAL INVARIANT: XGBoost never receives or reintroduces candidates rejected by hard constraints."""
    # Enable XGBoost in recommender
    recommender.config.xgboost_ranking_enabled = True
    recommender.ranking_dispatcher.enabled = True

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
        assert not any("tomato" in ing for ing in clean_ings), f"Violation: {rid} contains excluded tomato!"

    # Reset
    recommender.config.xgboost_ranking_enabled = False
    recommender.ranking_dispatcher.enabled = False


def test_zero_eligible_candidates_with_xgboost(recommender: KitchenPilotRecommender):
    """When hard constraints produce 0 eligible candidates, XGBoost produces 0 results safely."""
    recommender.config.xgboost_ranking_enabled = True
    recommender.ranking_dispatcher.enabled = True

    req_impossible = ConstraintRequest(
        nutrition=NutritionConstraints(max_calories=10.0, min_protein_g=200.0)
    )

    df = recommender.recommend(
        top_k=10,
        save_results=False,
        constraint_request=req_impossible,
    )
    assert df.empty

    # Reset
    recommender.config.xgboost_ranking_enabled = False
    recommender.ranking_dispatcher.enabled = False


# ============================================================================
# 5. FALLBACK BEHAVIOR TESTS
# ============================================================================

def test_fallback_when_xgboost_disabled(recommender: KitchenPilotRecommender):
    """When xgboost_ranking_enabled is False, recommender uses HybridRanker."""
    recommender.config.xgboost_ranking_enabled = False
    recommender.ranking_dispatcher.enabled = False

    df = recommender.recommend(
        available_ingredients=["paneer", "spinach"],
        top_k=5,
        save_results=False,
    )
    assert not df.empty
    assert len(df) <= 5
    assert recommender.ranking_dispatcher.last_ranker_used == "hybrid"


def test_fallback_when_model_corrupt_or_missing():
    """When model fails, RankingDispatcher automatically falls back to HybridRanker without crashing."""
    config = RecommendationConfig()
    hybrid = HybridRanker(config=config)
    corrupt_ranker = XGBoostRanker(model_path=Path("non_existent_model_file.json"))

    dispatcher = RankingDispatcher(
        xgboost_ranker=corrupt_ranker,
        hybrid_ranker=hybrid,
        enabled=True,
    )

    candidates = [
        ScoredCandidate("RECIPE_0001", "A", 0.5, 0.5, 0.5, 0.5, 1.0),
        ScoredCandidate("RECIPE_0002", "B", 0.8, 0.8, 0.8, 0.8, 1.0),
    ]
    context = RankingContext()

    ranked = dispatcher.rank_candidates(candidates, context, top_k=2)
    assert len(ranked) == 2
    # Verify fallback was triggered
    assert dispatcher.last_ranker_used == "hybrid"
    assert ranked[0].recipe_id == "RECIPE_0002"
