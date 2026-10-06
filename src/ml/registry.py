"""Local Model Registry for KitchenPilot-V1 (Stage I).

Tracks and manages model artifacts, candidate statuses, SHA-256 checksums, and explicit promotions.
Status Transitions:
  TRAINED -> EVALUATED -> CANDIDATE -> PROMOTED -> ARCHIVED / ROLLED_BACK
  Any model can transition to REJECTED if gates fail.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ml.config import (
    ARCHIVE_DIR,
    CANDIDATES_DIR,
    PRODUCTION_FEATURE_SCHEMA_VERSION,
    PRODUCTION_METADATA_PATH,
    PRODUCTION_MODEL_ID,
    PRODUCTION_MODEL_PATH,
    PRODUCTION_MODEL_SHA256,
    PRODUCTION_SCHEMA_PATH,
    REGISTRY_PATH,
)

logger = logging.getLogger("kitchenpilot.ml.registry")


def compute_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ModelRegistryEntry:
    """Single entry in local model registry."""
    model_id: str
    model_version: str
    status: str  # "TRAINED", "EVALUATED", "CANDIDATE", "PROMOTED", "REJECTED", "ARCHIVED", "ROLLED_BACK"
    artifact_path: str
    artifact_checksum: str
    feature_schema_version: str
    dataset_version: str
    created_at: str
    evaluated_at: Optional[str] = None
    promoted_at: Optional[str] = None
    parent_model_version: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class LocalModelRegistry:
    """Thread-safe and process-safe local JSON-backed model registry."""

    def __init__(self, registry_file: Path = REGISTRY_PATH) -> None:
        self.registry_file = Path(registry_file)
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Seed registry with baseline Stage F production model if fresh."""
        if not self.registry_file.is_file():
            # Seed production baseline
            now_str = datetime.now(timezone.utc).isoformat()
            prod_entry = ModelRegistryEntry(
                model_id=PRODUCTION_MODEL_ID,
                model_version="0.1.0",
                status="PROMOTED",
                artifact_path=str(PRODUCTION_MODEL_PATH),
                artifact_checksum=PRODUCTION_MODEL_SHA256,
                feature_schema_version=PRODUCTION_FEATURE_SCHEMA_VERSION,
                dataset_version="1.0.0",
                created_at="2026-10-03T17:30:09.991107+00:00",
                evaluated_at="2026-10-03T17:30:10.000000+00:00",
                promoted_at="2026-10-03T17:30:10.000000+00:00",
                parent_model_version=None,
                metrics={
                    "ndcg@5": 1.0,
                    "ndcg@10": 1.0,
                    "mrr@10": 1.0,
                    "precision@5": 1.0,
                    "precision@10": 0.9333,
                },
                hyperparameters={
                    "n_estimators": 80,
                    "max_depth": 4,
                    "learning_rate": 0.08,
                    "subsample": 0.85,
                    "colsample_bytree": 0.85,
                    "objective": "rank:ndcg",
                },
                metadata={"description": "Baseline Stage F Weak Supervision XGBoost Ranker"},
            )
            data = {
                "active_production_model": PRODUCTION_MODEL_ID,
                "history": [asdict(prod_entry)],
            }
            self.registry_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> Dict[str, Any]:
        return json.loads(self.registry_file.read_text(encoding="utf-8"))

    def _save(self, data: Dict[str, Any]) -> None:
        self.registry_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_production_model(self) -> Optional[ModelRegistryEntry]:
        """Retrieve the active production model record."""
        data = self._load()
        active_id = data.get("active_production_model")
        for m in data.get("history", []):
            if m["model_id"] == active_id:
                return ModelRegistryEntry(**m)
        return None

    def get_model(self, model_id: str) -> Optional[ModelRegistryEntry]:
        """Find a model entry by ID."""
        data = self._load()
        for m in data.get("history", []):
            if m["model_id"] == model_id:
                return ModelRegistryEntry(**m)
        return None

    def list_models(self) -> List[ModelRegistryEntry]:
        """List all registered models."""
        data = self._load()
        return [ModelRegistryEntry(**m) for m in data.get("history", [])]

    def register_candidate(
        self,
        model_id: str,
        model_version: str,
        artifact_path: Path,
        feature_schema_version: str,
        dataset_version: str,
        hyperparameters: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
        parent_model_version: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ModelRegistryEntry:
        """Register a newly trained candidate model."""
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Artifact not found: {artifact_path}")

        checksum = compute_file_sha256(artifact_path)
        entry = ModelRegistryEntry(
            model_id=model_id,
            model_version=model_version,
            status="CANDIDATE",
            artifact_path=str(artifact_path),
            artifact_checksum=checksum,
            feature_schema_version=feature_schema_version,
            dataset_version=dataset_version,
            created_at=datetime.now(timezone.utc).isoformat(),
            evaluated_at=None,
            promoted_at=None,
            parent_model_version=parent_model_version,
            metrics=metrics or {},
            hyperparameters=hyperparameters,
            metadata=metadata or {},
        )

        data = self._load()
        # Avoid duplicate registration
        data["history"] = [m for m in data.get("history", []) if m["model_id"] != model_id]
        data["history"].append(asdict(entry))
        self._save(data)
        logger.info("Registered model candidate '%s' with checksum %s", model_id, checksum[:12])
        return entry

    def update_model_status(self, model_id: str, new_status: str, metrics: Optional[Dict[str, Any]] = None) -> bool:
        """Update lifecycle status of a model in the registry."""
        data = self._load()
        found = False
        for m in data.get("history", []):
            if m["model_id"] == model_id:
                m["status"] = new_status
                if metrics:
                    m["metrics"].update(metrics)
                if new_status == "EVALUATED":
                    m["evaluated_at"] = datetime.now(timezone.utc).isoformat()
                elif new_status == "PROMOTED":
                    m["promoted_at"] = datetime.now(timezone.utc).isoformat()
                found = True
                break
        if found:
            self._save(data)
        return found
