"""Stage I Production ML Lifecycle, Data Sufficiency, and Model Registry Tests."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

from src.ml.config import (
    INTERACTION_PRECEDENCE,
    LABEL_GRADES,
    MIN_INTERACTIONS,
    PRODUCTION_MODEL_ID,
    PRODUCTION_MODEL_PATH,
    PRODUCTION_MODEL_SHA256,
)
from src.ml.data_quality import check_data_sufficiency, validate_training_data_quality
from src.ml.labels import assign_relevance_grade, resolve_conflicting_interactions
from src.ml.temporal_split import chronological_query_split, verify_temporal_leakage
from src.ml.registry import LocalModelRegistry, compute_file_sha256
from src.ml.promotion import promote_candidate_model, rollback_production_model


def test_empty_dataset_stops_safely():
    """Verify empty dataset triggers INSUFFICIENT_DATA and fails sufficiency check."""
    empty_df = pd.DataFrame()
    suff = check_data_sufficiency(empty_df)
    assert suff.is_sufficient is False
    assert suff.status == "INSUFFICIENT_DATA"
    assert len(suff.violations) > 0


def test_sparse_dataset_fails_sufficiency():
    """Verify dataset with fewer than required interactions fails sufficiency."""
    sparse_data = {
        "user_id": [1, 2, 3],
        "recipe_id": ["R00001", "R00002", "R00003"],
        "session_id": ["s1", "s2", "s3"],
        "feedback_type": ["LIKE", "COOKED", "SAVE"],
        "impression_timestamp": ["2026-10-01T10:00:00Z", "2026-10-02T10:00:00Z", "2026-10-03T10:00:00Z"],
    }
    df = pd.DataFrame(sparse_data)
    suff = check_data_sufficiency(df)
    assert suff.is_sufficient is False
    assert suff.status == "INSUFFICIENT_DATA"
    assert any("Total interactions" in v for v in suff.violations)


def test_relevance_label_assignment():
    """Verify graded relevance mapping policy."""
    assert assign_relevance_grade("COOKED") == 3
    assert assign_relevance_grade("SAVE") == 2
    assert assign_relevance_grade("LIKE") == 2
    assert assign_relevance_grade("IMPRESSION") == 1
    assert assign_relevance_grade(None) == 1
    assert assign_relevance_grade("DISLIKE") == 0
    assert assign_relevance_grade("HIDE") == 0


def test_conflict_resolution_negative_precedence():
    """Verify that negative feedback (HIDE, DISLIKE) deterministically overrides impressions or likes."""
    data = {
        "session_id": ["sess_1", "sess_1"],
        "recipe_id": ["R00001", "R00001"],
        "feedback_type": ["LIKE", "HIDE"],
        "impression_timestamp": ["2026-10-01T10:00:00Z", "2026-10-01T10:00:00Z"],
    }
    df = pd.DataFrame(data)
    resolved = resolve_conflicting_interactions(df)
    assert len(resolved) == 1
    assert resolved.iloc[0]["feedback_type"] == "HIDE"
    assert resolved.iloc[0]["relevance_label"] == 0


def test_temporal_split_chronological_ordering():
    """Verify that chronological splitting strictly separates query sessions without future leakage."""
    data = []
    # Create 20 distinct sessions spanning 20 consecutive days
    for day in range(1, 21):
        sess_id = f"session_{day:02d}"
        t_str = f"2026-10-{day:02d}T12:00:00Z"
        data.append({
            "session_id": sess_id,
            "user_id": day,
            "recipe_id": f"R{day:05d}",
            "impression_timestamp": t_str,
            "feedback_type": "COOKED" if day % 2 == 0 else "LIKE",
        })
    df = pd.DataFrame(data)

    train_df, val_df, test_df, cutoffs = chronological_query_split(df, train_ratio=0.7, val_ratio=0.15)
    assert len(train_df) == 14
    assert len(val_df) == 3
    assert len(test_df) == 3

    # Verify leakage check succeeds
    leakage = verify_temporal_leakage(train_df, val_df, test_df)
    assert leakage.passed is True
    assert leakage.future_timestamp_in_train == 0
    assert leakage.query_session_overlap == 0


def test_temporal_leakage_detection():
    """Verify that future timestamps in the train set are caught by verify_temporal_leakage."""
    train_df = pd.DataFrame({
        "session_id": ["s1"],
        "impression_timestamp": ["2026-10-25T00:00:00Z"],
    })
    val_df = pd.DataFrame({
        "session_id": ["s2"],
        "impression_timestamp": ["2026-10-10T00:00:00Z"],
    })
    test_df = pd.DataFrame({
        "session_id": ["s3"],
        "impression_timestamp": ["2026-10-15T00:00:00Z"],
    })
    leakage = verify_temporal_leakage(train_df, val_df, test_df)
    assert leakage.passed is False
    assert leakage.future_timestamp_in_train > 0


def test_model_registry_production_integrity(tmp_path: Path):
    """Verify that LocalModelRegistry correctly initializes, registers, and tracks production baseline."""
    reg_file = tmp_path / "test_registry.json"
    reg = LocalModelRegistry(registry_file=reg_file)

    prod = reg.get_production_model()
    assert prod is not None
    assert prod.model_id == PRODUCTION_MODEL_ID
    assert prod.status == "PROMOTED"
    assert prod.artifact_checksum == PRODUCTION_MODEL_SHA256


def test_promotion_and_rollback_lifecycle(tmp_path: Path):
    """Verify safe candidate registration, promotion, archive preservation, and rollback."""
    reg_file = tmp_path / "test_reg.json"
    reg = LocalModelRegistry(registry_file=reg_file)

    # Create dummy candidate artifact
    cand_path = tmp_path / "xgb_ranker_v0.2.0.json"
    cand_path.write_text('{"dummy": "model"}', encoding="utf-8")

    reg.register_candidate(
        model_id="xgb_ranker_v0.2.0",
        model_version="0.2.0",
        artifact_path=cand_path,
        feature_schema_version="1.0.0",
        dataset_version="1.0.0",
        hyperparameters={"n_estimators": 50},
    )

    cand = reg.get_model("xgb_ranker_v0.2.0")
    assert cand is not None
    assert cand.status == "CANDIDATE"

    # Promote candidate
    success, msg = promote_candidate_model("xgb_ranker_v0.2.0", registry=reg)
    assert success is True
    assert reg.get_production_model().model_id == "xgb_ranker_v0.2.0"
    assert reg.get_model(PRODUCTION_MODEL_ID).status == "ARCHIVED"

    # Rollback to baseline
    success_rb, msg_rb = rollback_production_model(registry=reg)
    assert success_rb is True
    assert reg.get_production_model().model_id == PRODUCTION_MODEL_ID
    assert reg.get_model("xgb_ranker_v0.2.0").status == "ROLLED_BACK"
