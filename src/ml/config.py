"""ML Configuration and Data Sufficiency Thresholds for Stage I.

Defines:
1. Strict, conservative thresholds for real user interaction training data sufficiency.
2. Label policy, grade assignments, and conflict resolution precedence.
3. Feature schema version and model registry directory structure.
4. Model candidate acceptance gates for offline evaluation vs production.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Registry & Storage Paths
ML_DIR = PROJECT_ROOT / "models" / "ml_lifecycle"
REGISTRY_PATH = ML_DIR / "model_registry.json"
CANDIDATES_DIR = ML_DIR / "candidates"
ARCHIVE_DIR = ML_DIR / "archive"
EVALUATION_REPORTS_DIR = ML_DIR / "evaluations"

# Production Baseline Constants (Stage F)
PRODUCTION_MODEL_ID = "xgb_ranker_v0.1.0"
PRODUCTION_MODEL_PATH = PROJECT_ROOT / "models" / "ranking" / "xgboost_ranker.json"
PRODUCTION_SCHEMA_PATH = PROJECT_ROOT / "models" / "ranking" / "feature_schema.json"
PRODUCTION_METADATA_PATH = PROJECT_ROOT / "models" / "ranking" / "metadata.json"
PRODUCTION_MODEL_SHA256 = "8d00370fb80f81de6e889a1c6b75290063284a3964de85a2a9acc502b0d6677b"
PRODUCTION_FEATURE_SCHEMA_VERSION = "1.0.0"
PRODUCTION_DATASET_VERSION = "1.0.0"

# Conservative Data Sufficiency Thresholds for Controlled Candidate Retraining
# A candidate model CANNOT be trained if any threshold is unmet.
MIN_INTERACTIONS: int = int(os.getenv("ML_MIN_INTERACTIONS", "200"))
MIN_USERS: int = int(os.getenv("ML_MIN_USERS", "20"))
MIN_RECIPES: int = int(os.getenv("ML_MIN_RECIPES", "50"))
MIN_QUERY_GROUPS: int = int(os.getenv("ML_MIN_QUERY_GROUPS", "30"))
MIN_POSITIVE_LABELS: int = int(os.getenv("ML_MIN_POSITIVE_LABELS", "40"))
MIN_NEGATIVE_LABELS: int = int(os.getenv("ML_MIN_NEGATIVE_LABELS", "10"))
MIN_DAYS_OF_DATA: int = int(os.getenv("ML_MIN_DAYS_OF_DATA", "7"))

# Graded Relevance Mapping Policy
# 3: Highest engagement (COOKED)
# 2: High engagement / positive (SAVE, LIKE)
# 1: Baseline examined impression without explicit feedback
# 0: Explicit negative engagement (DISLIKE, HIDE)
LABEL_GRADES: Dict[str, int] = {
    "COOKED": 3,
    "SAVE": 2,
    "LIKE": 2,
    "IMPRESSION": 1,
    "DISLIKE": 0,
    "HIDE": 0,
}

# Conflict Resolution Precedence (Deterministic when multiple interactions exist for same session + recipe)
# Negative interactions take top priority to avoid recommending disliked items,
# followed by highest active positive engagement.
INTERACTION_PRECEDENCE: List[str] = [
    "HIDE",
    "DISLIKE",
    "COOKED",
    "SAVE",
    "LIKE",
    "IMPRESSION",
]

# Promotion Acceptance Criteria (Quality & Safety Gates)
# Candidate model must satisfy ALL gates to be eligible for promotion.
GATE_MAX_HARD_CONSTRAINT_VIOLATIONS: int = 0
GATE_MIN_NDCG5_IMPROVEMENT_PCT: float = 0.0  # Must not degrade production NDCG@5
GATE_MIN_MRR10_IMPROVEMENT_PCT: float = 0.0  # Must not degrade production MRR@10
GATE_MAX_ZERO_RESULT_RATE_PCT: float = 0.0   # Must produce valid candidates
GATE_MAX_INFERENCE_LATENCY_P95_MS: float = 250.0  # Inference speed safety gate
