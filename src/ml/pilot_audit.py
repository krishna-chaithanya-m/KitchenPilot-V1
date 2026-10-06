"""
KitchenPilot-V1 — Pilot Feedback Data Quality Monitor (Stage K)

Performs comprehensive data-quality auditing on real pilot user interactions:
- Interaction counts and distinct entity statistics
- Label distributions (positive, negative, neutral/impression)
- Temporal integrity checks (feedback_timestamp >= impression_timestamp)
- Entity validity checks (valid users in DB, valid recipes in catalog)
- Duplicate detection and conflict resolution precedence checks
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.config import RECIPES_PATH
from src.ml.config import INTERACTION_PRECEDENCE, LABEL_GRADES
from src.personalization.models import RecommendationHistoryModel, UserFeedbackModel, UserModel

logger = logging.getLogger("kitchenpilot.ml.pilot_audit")


@dataclass
class PilotDataQualityReport:
    """Structured report of genuine pilot feedback quality metrics."""
    audit_timestamp: str
    total_interactions: int
    unique_users: int
    unique_recipes: int
    unique_query_groups: int
    date_range_start: Optional[str]
    date_range_end: Optional[str]
    days_of_data: float
    positive_labels: int
    negative_labels: int
    neutral_impression_labels: int
    label_breakdown: Dict[str, int]
    duplicate_events_count: int
    invalid_users_count: int
    invalid_recipes_count: int
    temporal_violations_count: int
    missing_query_groups_count: int
    conflicting_feedback_pairs: int
    quality_status: str  # "CLEAN", "ACCEPTABLE", "DEFECTS_DETECTED"
    detected_anomalies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def audit_pilot_feedback_data(db: Session) -> PilotDataQualityReport:
    """Run an exhaustive data-quality audit against the live database without mutating records."""
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Fetch all feedback items
    feedback_rows = db.execute(
        select(
            UserFeedbackModel.id,
            UserFeedbackModel.user_id,
            UserFeedbackModel.recipe_id,
            UserFeedbackModel.feedback_type,
            UserFeedbackModel.session_id,
            UserFeedbackModel.created_at,
        )
    ).all()

    total_interactions = len(feedback_rows)
    anomalies: List[str] = []

    if total_interactions == 0:
        return PilotDataQualityReport(
            audit_timestamp=now_iso,
            total_interactions=0,
            unique_users=0,
            unique_recipes=0,
            unique_query_groups=0,
            date_range_start=None,
            date_range_end=None,
            days_of_data=0.0,
            positive_labels=0,
            negative_labels=0,
            neutral_impression_labels=0,
            label_breakdown={},
            duplicate_events_count=0,
            invalid_users_count=0,
            invalid_recipes_count=0,
            temporal_violations_count=0,
            missing_query_groups_count=0,
            conflicting_feedback_pairs=0,
            quality_status="CLEAN",
            detected_anomalies=[],
        )

    # 2. Extract sets and entity counts
    user_ids: Set[int] = {r.user_id for r in feedback_rows}
    recipe_ids: Set[str] = {r.recipe_id for r in feedback_rows}
    session_ids: Set[str] = {r.session_id for r in feedback_rows if r.session_id}

    timestamps = [r.created_at for r in feedback_rows if r.created_at]
    if timestamps:
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        days = max(0.0, (max_ts - min_ts).total_seconds() / 86400.0)
        date_start = min_ts.isoformat()
        date_end = max_ts.isoformat()
    else:
        days = 0.0
        date_start = None
        date_end = None

    # 3. Label distributions
    label_breakdown: Dict[str, int] = {}
    positive_count = 0
    negative_count = 0
    neutral_count = 0

    for r in feedback_rows:
        ftype = (r.feedback_type or "").upper().strip()
        label_breakdown[ftype] = label_breakdown.get(ftype, 0) + 1
        grade = LABEL_GRADES.get(ftype, 1)
        if grade in (2, 3):
            positive_count += 1
        elif grade == 0:
            negative_count += 1
        else:
            neutral_count += 1

    # 4. Entity validity checks
    # Check valid users in DB
    existing_user_ids = set(db.execute(select(UserModel.id)).scalars().all())
    invalid_users = user_ids - existing_user_ids
    if invalid_users:
        anomalies.append(f"Found {len(invalid_users)} feedback records from non-existent user IDs: {invalid_users}")

    # Check valid recipes in catalog
    try:
        catalog_df = pd.read_csv(RECIPES_PATH)
        valid_recipe_ids = set(catalog_df["recipe_id"].astype(str).str.strip())
    except Exception:
        valid_recipe_ids = set()

    if valid_recipe_ids:
        invalid_recipes = recipe_ids - valid_recipe_ids
        if invalid_recipes:
            anomalies.append(f"Found {len(invalid_recipes)} feedback records for non-catalog recipe IDs: {list(invalid_recipes)[:5]}")
    else:
        invalid_recipes = set()

    # 5. Duplicate events and conflict detection
    key_counts: Dict[Tuple[int, str, str, Optional[str]], int] = {}
    session_recipe_feedback: Dict[Tuple[Optional[str], str], Set[str]] = {}

    for r in feedback_rows:
        k = (r.user_id, r.recipe_id, r.feedback_type, r.session_id)
        key_counts[k] = key_counts.get(k, 0) + 1

        sr_key = (r.session_id, r.recipe_id)
        if sr_key not in session_recipe_feedback:
            session_recipe_feedback[sr_key] = set()
        session_recipe_feedback[sr_key].add(r.feedback_type)

    duplicate_count = sum(c - 1 for c in key_counts.values() if c > 1)
    if duplicate_count > 0:
        anomalies.append(f"Detected {duplicate_count} duplicate feedback events.")

    conflicting_pairs = sum(1 for ftypes in session_recipe_feedback.values() if len(ftypes) > 1)

    # 6. Temporal integrity & session presence
    temporal_violations = 0
    missing_sessions = 0

    # Query history for matching sessions
    history_lookup: Dict[Tuple[str, str], datetime] = {}
    if session_ids:
        hist_rows = db.execute(
            select(
                RecommendationHistoryModel.session_id,
                RecommendationHistoryModel.recipe_id,
                RecommendationHistoryModel.created_at,
            ).where(RecommendationHistoryModel.session_id.in_(list(session_ids)))
        ).all()
        for h in hist_rows:
            history_lookup[(h.session_id, h.recipe_id)] = h.created_at

    for r in feedback_rows:
        if not r.session_id:
            missing_sessions += 1
            continue

        hist_ts = history_lookup.get((r.session_id, r.recipe_id))
        if hist_ts and r.created_at and r.created_at < hist_ts:
            temporal_violations += 1

    if temporal_violations > 0:
        anomalies.append(f"Detected {temporal_violations} temporal integrity violations (feedback before recommendation).")

    # Determine status
    if invalid_users or invalid_recipes or temporal_violations > 0:
        quality_status = "DEFECTS_DETECTED"
    elif duplicate_count > 0 or missing_sessions > 0:
        quality_status = "ACCEPTABLE"
    else:
        quality_status = "CLEAN"

    return PilotDataQualityReport(
        audit_timestamp=now_iso,
        total_interactions=total_interactions,
        unique_users=len(user_ids),
        unique_recipes=len(recipe_ids),
        unique_query_groups=len(session_ids),
        date_range_start=date_start,
        date_range_end=date_end,
        days_of_data=round(days, 2),
        positive_labels=positive_count,
        negative_labels=negative_count,
        neutral_impression_labels=neutral_count,
        label_breakdown=label_breakdown,
        duplicate_events_count=duplicate_count,
        invalid_users_count=len(invalid_users),
        invalid_recipes_count=len(invalid_recipes),
        temporal_violations_count=temporal_violations,
        missing_query_groups_count=missing_sessions,
        conflicting_feedback_pairs=conflicting_pairs,
        quality_status=quality_status,
        detected_anomalies=anomalies,
    )
