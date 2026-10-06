"""Interaction labeling, graded relevance assignment, and deterministic conflict resolution for Stage I."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd

from src.ml.config import INTERACTION_PRECEDENCE, LABEL_GRADES

logger = logging.getLogger("kitchenpilot.ml.labels")


def assign_relevance_grade(feedback_type: Optional[str]) -> int:
    """Map explicit feedback string to integer relevance grade.
    
    Grading Policy:
      COOKED     -> 3 (highest positive engagement)
      SAVE, LIKE -> 2 (positive preference)
      IMPRESSION -> 1 (examined baseline, no explicit feedback)
      DISLIKE, HIDE -> 0 (negative engagement)
    """
    if not feedback_type or pd.isna(feedback_type):
        return LABEL_GRADES["IMPRESSION"]

    key = str(feedback_type).strip().upper()
    return LABEL_GRADES.get(key, LABEL_GRADES["IMPRESSION"])


def resolve_conflicting_interactions(df: pd.DataFrame) -> pd.DataFrame:
    """Deterministically resolve multiple interactions for the same (session_id, recipe_id).
    
    Resolution Precedence:
      HIDE > DISLIKE > COOKED > SAVE > LIKE > IMPRESSION
    
    Rationale:
      Safety first: Negative signals take precedence to prevent recommending disliked or hidden recipes.
      Otherwise, highest positive action (COOKED over SAVE over LIKE) is chosen.
    """
    if df.empty or "session_id" not in df.columns or "recipe_id" not in df.columns:
        return df

    # Normalize feedback_type
    df_clean = df.copy()
    if "feedback_type" not in df_clean.columns:
        df_clean["feedback_type"] = "IMPRESSION"
    else:
        df_clean["feedback_type"] = df_clean["feedback_type"].fillna("IMPRESSION").astype(str).str.upper()

    # Create categorical precedence rank
    precedence_map = {action: idx for idx, action in enumerate(INTERACTION_PRECEDENCE)}
    # Any unknown action gets lowest precedence
    df_clean["_prec_rank"] = df_clean["feedback_type"].map(lambda a: precedence_map.get(a, 99))

    # Sort so that highest precedence comes first within each (session_id, recipe_id)
    df_sorted = df_clean.sort_values(by=["session_id", "recipe_id", "_prec_rank"])

    # Drop duplicate interactions, keeping the top precedence
    resolved = df_sorted.drop_duplicates(subset=["session_id", "recipe_id"], keep="first").copy()
    resolved = resolved.drop(columns=["_prec_rank"])

    # Re-calculate relevance_label based on resolved feedback_type
    resolved["relevance_label"] = resolved["feedback_type"].map(assign_relevance_grade)
    return resolved
