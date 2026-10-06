"""Data quality auditing, anomaly detection, and sufficiency gates for real interaction training data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.ml.config import (
    MIN_DAYS_OF_DATA,
    MIN_INTERACTIONS,
    MIN_NEGATIVE_LABELS,
    MIN_POSITIVE_LABELS,
    MIN_QUERY_GROUPS,
    MIN_RECIPES,
    MIN_USERS,
)

logger = logging.getLogger("kitchenpilot.ml.data_quality")


@dataclass
class SufficiencyCheckResult:
    """Result of data sufficiency evaluation."""
    is_sufficient: bool
    status: str  # "SUFFICIENT" or "INSUFFICIENT_DATA"
    total_interactions: int
    unique_users: int
    unique_recipes: int
    unique_queries: int
    positive_labels: int
    negative_labels: int
    days_of_data: float
    violations: List[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class TrainingDataQualityReport:
    """Comprehensive data health audit report prior to dataset generation."""
    is_valid: bool
    total_records: int
    missing_user_ids: int
    missing_recipe_ids: int
    missing_session_ids: int
    duplicate_records: int
    temporal_inversions: int
    invalid_feedback_types: int
    anomalies: List[str] = field(default_factory=list)
    sufficiency: Optional[SufficiencyCheckResult] = None


def check_data_sufficiency(df: pd.DataFrame) -> SufficiencyCheckResult:
    """Evaluate whether recorded interaction dataset satisfies production training volume thresholds."""
    if df.empty:
        return SufficiencyCheckResult(
            is_sufficient=False,
            status="INSUFFICIENT_DATA",
            total_interactions=0,
            unique_users=0,
            unique_recipes=0,
            unique_queries=0,
            positive_labels=0,
            negative_labels=0,
            days_of_data=0.0,
            violations=["Dataset is completely empty (0 interaction events)."],
            summary="Insufficient real-world interaction data for statistically meaningful training.",
        )

    violations: List[str] = []

    total_interactions = len(df)
    unique_users = df["user_id"].nunique(dropna=True) if "user_id" in df.columns else 0
    unique_recipes = df["recipe_id"].nunique(dropna=True) if "recipe_id" in df.columns else 0
    unique_queries = df["session_id"].nunique(dropna=True) if "session_id" in df.columns else 0

    # Count positive (label >= 2 or COOKED, SAVE, LIKE)
    pos_count = 0
    neg_count = 0
    if "feedback_type" in df.columns:
        fb_series = df["feedback_type"].dropna().str.upper()
        pos_count = int(fb_series.isin(["COOKED", "SAVE", "LIKE"]).sum())
        neg_count = int(fb_series.isin(["DISLIKE", "HIDE"]).sum())
    elif "relevance_label" in df.columns:
        pos_count = int((df["relevance_label"] >= 2).sum())
        neg_count = int((df["relevance_label"] == 0).sum())

    # Temporal span (days)
    days_span = 0.0
    if "impression_timestamp" in df.columns and not df["impression_timestamp"].isna().all():
        try:
            ts = pd.to_datetime(df["impression_timestamp"].dropna())
            days_span = round((ts.max() - ts.min()).total_seconds() / 86400.0, 2)
        except Exception:
            days_span = 0.0

    if total_interactions < MIN_INTERACTIONS:
        violations.append(f"Total interactions ({total_interactions}) < required minimum ({MIN_INTERACTIONS}).")
    if unique_users < MIN_USERS:
        violations.append(f"Unique users ({unique_users}) < required minimum ({MIN_USERS}).")
    if unique_recipes < MIN_RECIPES:
        violations.append(f"Unique recipes ({unique_recipes}) < required minimum ({MIN_RECIPES}).")
    if unique_queries < MIN_QUERY_GROUPS:
        violations.append(f"Unique query/session groups ({unique_queries}) < required minimum ({MIN_QUERY_GROUPS}).")
    if pos_count < MIN_POSITIVE_LABELS:
        violations.append(f"Positive labels ({pos_count}) < required minimum ({MIN_POSITIVE_LABELS}).")
    if neg_count < MIN_NEGATIVE_LABELS:
        violations.append(f"Negative labels ({neg_count}) < required minimum ({MIN_NEGATIVE_LABELS}).")
    if days_span < MIN_DAYS_OF_DATA:
        violations.append(f"Temporal span ({days_span} days) < required minimum ({MIN_DAYS_OF_DATA} days).")

    is_suff = len(violations) == 0
    status_str = "SUFFICIENT" if is_suff else "INSUFFICIENT_DATA"
    summary_str = (
        "Dataset satisfies all conservative data sufficiency criteria for candidate retraining."
        if is_suff
        else "Insufficient real-world interaction data for statistically meaningful training."
    )

    return SufficiencyCheckResult(
        is_sufficient=is_suff,
        status=status_str,
        total_interactions=total_interactions,
        unique_users=unique_users,
        unique_recipes=unique_recipes,
        unique_queries=unique_queries,
        positive_labels=pos_count,
        negative_labels=neg_count,
        days_of_data=days_span,
        violations=violations,
        summary=summary_str,
    )


def validate_training_data_quality(df: pd.DataFrame) -> TrainingDataQualityReport:
    """Perform rigorous quality audit of raw interactions prior to candidate feature generation."""
    anomalies: List[str] = []

    if df.empty:
        suff = check_data_sufficiency(df)
        return TrainingDataQualityReport(
            is_valid=False,
            total_records=0,
            missing_user_ids=0,
            missing_recipe_ids=0,
            missing_session_ids=0,
            duplicate_records=0,
            temporal_inversions=0,
            invalid_feedback_types=0,
            anomalies=["Dataset is empty."],
            sufficiency=suff,
        )

    n = len(df)
    missing_u = int(df["user_id"].isna().sum()) if "user_id" in df.columns else n
    missing_r = int(df["recipe_id"].isna().sum()) if "recipe_id" in df.columns else n
    missing_s = int(df["session_id"].isna().sum()) if "session_id" in df.columns else n

    if missing_u > 0:
        anomalies.append(f"Found {missing_u} records with null user_id.")
    if missing_r > 0:
        anomalies.append(f"Found {missing_r} records with null recipe_id.")
    if missing_s > 0:
        anomalies.append(f"Found {missing_s} records with null session_id.")

    # Duplicate check on (session_id, recipe_id)
    dup_count = 0
    if "session_id" in df.columns and "recipe_id" in df.columns:
        dup_count = int(df.duplicated(subset=["session_id", "recipe_id"]).sum())
        if dup_count > 0:
            anomalies.append(f"Found {dup_count} duplicate recipe impressions inside identical sessions.")

    # Temporal sequence check (impression_timestamp <= feedback_timestamp)
    inv_count = 0
    if "impression_timestamp" in df.columns and "feedback_timestamp" in df.columns:
        paired = df.dropna(subset=["impression_timestamp", "feedback_timestamp"])
        for _, row in paired.iterrows():
            try:
                imp = pd.to_datetime(row["impression_timestamp"])
                fb = pd.to_datetime(row["feedback_timestamp"])
                if fb < imp:
                    inv_count += 1
            except Exception:
                pass
        if inv_count > 0:
            anomalies.append(f"Found {inv_count} events where feedback timestamp precedes impression timestamp.")

    # Invalid feedback type values
    invalid_fb = 0
    valid_types = {"COOKED", "SAVE", "LIKE", "DISLIKE", "HIDE", "NONE", ""}
    if "feedback_type" in df.columns:
        raw_fb = df["feedback_type"].fillna("").astype(str).str.upper()
        invalid_fb = int((~raw_fb.isin(valid_types)).sum())
        if invalid_fb > 0:
            anomalies.append(f"Found {invalid_fb} unrecognized feedback types.")

    suff = check_data_sufficiency(df)
    # Data is considered structurally valid if critical missingness is 0 and no temporal inversions exist
    is_struct_valid = (missing_u == 0 and missing_r == 0 and missing_s == 0 and inv_count == 0 and invalid_fb == 0)

    return TrainingDataQualityReport(
        is_valid=is_struct_valid,
        total_records=n,
        missing_user_ids=missing_u,
        missing_recipe_ids=missing_r,
        missing_session_ids=missing_s,
        duplicate_records=dup_count,
        temporal_inversions=inv_count,
        invalid_feedback_types=invalid_fb,
        anomalies=anomalies,
        sufficiency=suff,
    )
