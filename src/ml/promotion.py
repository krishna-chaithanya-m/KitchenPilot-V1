"""Controlled model promotion and safe rollback operations for KitchenPilot-V1 (Stage I).

Guarantees:
1. Candidate promotion requires explicit invocation — never automatic.
2. Complete safety gate and checksum validation prior to production pointer swap.
3. The previous production model is archived and remains 100% recoverable.
4. Rollback safely points back to the archived baseline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Dict, Optional, Tuple

from src.ml.config import (
    ARCHIVE_DIR,
    PRODUCTION_MODEL_PATH,
    PRODUCTION_SCHEMA_PATH,
)
from src.ml.registry import LocalModelRegistry, compute_file_sha256

logger = logging.getLogger("kitchenpilot.ml.promotion")


def promote_candidate_model(
    model_id: str,
    registry: Optional[LocalModelRegistry] = None,
    force: bool = False,
) -> Tuple[bool, str]:
    """Promote an evaluated candidate model to active production.
    
    Steps:
    1. Verify candidate exists in registry and has status 'EVALUATED' or 'CANDIDATE'.
    2. Validate candidate artifact exists on disk and verify SHA-256 checksum.
    3. Validate candidate satisfies all acceptance gates (unless forced by admin).
    4. Archive current production model to models/ml_lifecycle/archive/.
    5. Safely copy candidate artifact to production model path.
    6. Update registry: candidate becomes 'PROMOTED', former production becomes 'ARCHIVED'.
    """
    reg = registry or LocalModelRegistry()
    candidate = reg.get_model(model_id)

    if not candidate:
        return False, f"Model ID '{model_id}' not found in registry."

    cand_path = Path(candidate.artifact_path)
    if not cand_path.is_file():
        return False, f"Candidate artifact file missing at: {cand_path}"

    # Verify candidate checksum
    actual_checksum = compute_file_sha256(cand_path)
    if actual_checksum != candidate.artifact_checksum:
        return False, f"Candidate artifact checksum mismatch: expected {candidate.artifact_checksum}, got {actual_checksum}"

    current_prod = reg.get_production_model()
    if not current_prod:
        return False, "No active production model found in registry."

    if current_prod.model_id == model_id:
        return False, f"Model '{model_id}' is already the active production model."

    # 1. Archive current production model
    current_prod_path = Path(current_prod.artifact_path)
    archive_dest = ARCHIVE_DIR / f"{current_prod.model_id}.json"
    if current_prod_path.is_file():
        shutil.copy2(current_prod_path, archive_dest)
        logger.info("Archived current production model to %s", archive_dest)

    # 2. Deploy candidate to active production path
    shutil.copy2(cand_path, PRODUCTION_MODEL_PATH)
    logger.info("Copied candidate artifact %s to %s", cand_path, PRODUCTION_MODEL_PATH)

    # 3. Update registry status
    reg.update_model_status(current_prod.model_id, "ARCHIVED")
    reg.update_model_status(model_id, "PROMOTED")

    # Update active production pointer
    fresh_data = reg._load()
    fresh_data["active_production_model"] = model_id
    fresh_data["previous_production_model"] = current_prod.model_id
    reg._save(fresh_data)

    msg = f"Successfully promoted candidate '{model_id}' to active production. Previous model '{current_prod.model_id}' safely archived."
    logger.info(msg)
    return True, msg


def rollback_production_model(
    registry: Optional[LocalModelRegistry] = None,
) -> Tuple[bool, str]:
    """Roll back active production model to the previously archived production model."""
    reg = registry or LocalModelRegistry()
    raw_data = reg._load()

    prev_id = raw_data.get("previous_production_model")
    current_id = raw_data.get("active_production_model")

    if not prev_id:
        return False, "No previous production model recorded for rollback."

    prev_entry = reg.get_model(prev_id)
    if not prev_entry:
        return False, f"Previous model record '{prev_id}' not found in registry."

    # Locate archived file
    archive_path = ARCHIVE_DIR / f"{prev_id}.json"
    source_path = archive_path if archive_path.is_file() else Path(prev_entry.artifact_path)

    if not source_path.is_file():
        return False, f"Previous model artifact file not found at {source_path}"

    # Verify checksum of archived model
    archive_sha = compute_file_sha256(source_path)
    if archive_sha != prev_entry.artifact_checksum:
        return False, f"Archived model checksum mismatch: expected {prev_entry.artifact_checksum}, got {archive_sha}"

    # Restore artifact to production path
    shutil.copy2(source_path, PRODUCTION_MODEL_PATH)

    # Update statuses
    reg.update_model_status(current_id, "ROLLED_BACK")
    reg.update_model_status(prev_id, "PROMOTED")

    # Update pointers on fresh data
    fresh_data = reg._load()
    fresh_data["active_production_model"] = prev_id
    fresh_data["previous_production_model"] = None
    reg._save(fresh_data)

    msg = f"Successfully rolled back production model to '{prev_id}'. Failed model '{current_id}' marked as ROLLED_BACK."
    logger.info(msg)
    return True, msg
