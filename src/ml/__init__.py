"""Production ML Lifecycle Module for KitchenPilot-V1 (Stage I)."""

from src.ml.config import (
    MIN_INTERACTIONS,
    MIN_USERS,
    MIN_RECIPES,
    MIN_QUERY_GROUPS,
    MIN_POSITIVE_LABELS,
    MIN_NEGATIVE_LABELS,
    MIN_DAYS_OF_DATA,
    LABEL_GRADES,
    INTERACTION_PRECEDENCE,
    PRODUCTION_MODEL_ID,
)
from src.ml.data_quality import check_data_sufficiency, validate_training_data_quality
from src.ml.labels import assign_relevance_grade, resolve_conflicting_interactions
from src.ml.temporal_split import chronological_query_split, verify_temporal_leakage
from src.ml.registry import LocalModelRegistry, compute_file_sha256
from src.ml.evaluation import compare_models
from src.ml.promotion import promote_candidate_model, rollback_production_model
from src.ml.drift import compute_offline_drift

__all__ = [
    "MIN_INTERACTIONS",
    "MIN_USERS",
    "MIN_RECIPES",
    "MIN_QUERY_GROUPS",
    "MIN_POSITIVE_LABELS",
    "MIN_NEGATIVE_LABELS",
    "MIN_DAYS_OF_DATA",
    "LABEL_GRADES",
    "INTERACTION_PRECEDENCE",
    "PRODUCTION_MODEL_ID",
    "check_data_sufficiency",
    "validate_training_data_quality",
    "assign_relevance_grade",
    "resolve_conflicting_interactions",
    "chronological_query_split",
    "verify_temporal_leakage",
    "LocalModelRegistry",
    "compute_file_sha256",
    "compare_models",
    "promote_candidate_model",
    "rollback_production_model",
    "compute_offline_drift",
]
