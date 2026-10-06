"""Stage F XGBoost Learning-to-Rank Subsystem for KitchenPilot-V1.

Provides feature extraction, native GBDT ranking, deterministic tie-breaking,
IR metrics, and mandatory fallback to deterministic HybridRanker.
"""

from src.ranking.dataset import (
    DATASET_VERSION,
    RankingDatasetBuilder,
    compute_weak_relevance_label,
)
from src.ranking.fallback import RankingDispatcher
from src.ranking.features import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    FeatureExtractor,
    RankingContext,
)
from src.ranking.metrics import (
    dcg_at_k,
    evaluate_query_ranking,
    mrr_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from src.ranking.xgboost_ranker import XGBoostRanker

__all__ = [
    "DATASET_VERSION",
    "FEATURE_NAMES",
    "FEATURE_SCHEMA_VERSION",
    "FeatureExtractor",
    "RankingContext",
    "RankingDatasetBuilder",
    "RankingDispatcher",
    "XGBoostRanker",
    "compute_weak_relevance_label",
    "dcg_at_k",
    "evaluate_query_ranking",
    "mrr_at_k",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
]
