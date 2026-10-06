"""XGBoost Learning-to-Rank inference engine for Stage F.

Implements:
1. Native XGBoost model loading (.json format)
2. Schema validation guards (feature order and count verification)
3. Deterministic tie-breaking (XGBoost score -> BGE score -> TF-IDF score -> recipe_id)
4. Model health validation (finite outputs, NaN/Inf checks, candidate count preservation)
5. Explainability metadata preservation
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import xgboost as xgb

from src.ranking.features import FEATURE_NAMES, FeatureExtractor, RankingContext

logger = logging.getLogger("kitchenpilot.ranking.xgboost")

DEFAULT_MODEL_PATH = Path("models/ranking/xgboost_ranker.json")
DEFAULT_SCHEMA_PATH = Path("models/ranking/feature_schema.json")
DEFAULT_METADATA_PATH = Path("models/ranking/metadata.json")


class XGBoostRanker:
    """Production Learning-to-Rank inference engine using XGBoost GBDT."""

    def __init__(
        self,
        model_path: Path = DEFAULT_MODEL_PATH,
        schema_path: Path = DEFAULT_SCHEMA_PATH,
        metadata_path: Path = DEFAULT_METADATA_PATH,
        feature_extractor: Optional[FeatureExtractor] = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.schema_path = Path(schema_path)
        self.metadata_path = Path(metadata_path)
        self.feature_extractor = feature_extractor or FeatureExtractor()

        self._model: Optional[xgb.Booster] = None
        self._feature_names: List[str] = list(FEATURE_NAMES)
        self._metadata: Dict[str, Any] = {}
        self._is_loaded: bool = False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded and self._model is not None

    def load_model(self) -> None:
        """Load and validate model artifact, feature schema, and metadata."""
        if not self.model_path.is_file():
            raise FileNotFoundError(f"XGBoost ranking model artifact not found at: {self.model_path}")

        # 1. Load feature schema
        if self.schema_path.is_file():
            with open(self.schema_path, "r", encoding="utf-8") as f:
                schema_data = json.load(f)
                loaded_features = schema_data.get("feature_names", [])
                if loaded_features != self._feature_names:
                    logger.warning("Feature names in schema differ from codebase. Using schema definition.")
                    self._feature_names = loaded_features

        # 2. Load metadata
        if self.metadata_path.is_file():
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)

        # 3. Load native XGBoost model
        booster = xgb.Booster()
        booster.load_model(str(self.model_path))
        self._model = booster
        self._is_loaded = True
        logger.info("Loaded XGBoost ranking model successfully from %s", self.model_path)

    def rank(
        self,
        candidate_recipe_ids: Sequence[str],
        context: RankingContext,
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        """Rank eligible candidates using the trained XGBoost model with deterministic tie-breaking.

        Returns:
            List of (recipe_id, xgboost_score) ordered by descending rank.
        """
        if not candidate_recipe_ids:
            return []

        if not self.is_loaded:
            self.load_model()

        assert self._model is not None

        # 1. Feature extraction
        feature_matrix, _ = self.feature_extractor.extract_features(candidate_recipe_ids, context)

        # 2. Validate feature matrix dimensions
        if feature_matrix.shape[1] != len(self._feature_names):
            raise ValueError(
                f"Feature dimension mismatch: expected {len(self._feature_names)}, got {feature_matrix.shape[1]}"
            )

        # 3. Predict ranking scores
        dmat = xgb.DMatrix(feature_matrix, feature_names=self._feature_names)
        raw_scores = self._model.predict(dmat)

        # 4. Model quality guards (finite values, NaN/Inf checks)
        if not np.all(np.isfinite(raw_scores)):
            raise ValueError("XGBoost prediction yielded non-finite scores (NaN or Inf).")

        if len(raw_scores) != len(candidate_recipe_ids):
            raise ValueError(
                f"Candidate count mismatch: input {len(candidate_recipe_ids)}, predicted {len(raw_scores)}"
            )

        # 5. Deterministic multi-tier tie-breaking:
        # Tier 1: XGBoost score descending
        # Tier 2: BGE semantic similarity descending
        # Tier 3: TF-IDF similarity descending
        # Tier 4: recipe_id ascending
        candidate_records = []
        for i, rid in enumerate(candidate_recipe_ids):
            score = float(raw_scores[i])
            bge_s = float(context.bge_candidates.get(rid, 0.0))
            tfidf_s = float(context.tfidf_candidates.get(rid, 0.0))
            candidate_records.append({
                "recipe_id": rid,
                "score": score,
                "bge_score": bge_s,
                "tfidf_score": tfidf_s,
            })

        candidate_records.sort(
            key=lambda x: (-x["score"], -x["bge_score"], -x["tfidf_score"], x["recipe_id"])
        )

        ranked = [(rec["recipe_id"], rec["score"]) for rec in candidate_records[:top_k]]
        return ranked
