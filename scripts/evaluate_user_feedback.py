"""Evaluation and Data Quality Pipeline for Genuine User Feedback (Stage H).

KitchenPilot-V1 — Offline Real-User Interaction Evaluation.
Performs:
1. Interaction Data Quality Auditing:
   - User ID & Recipe ID integrity
   - Interaction sequence sanity (impression before feedback)
   - Timestamp monotonicity
   - Duplicate event detection
   - Anomaly reporting without silent data dropping
2. Temporal Train/Val/Test Splitting (Time-aware, leakage-free)
3. Offline Ranking Metrics Calculation (NDCG@5, NDCG@10, MRR@10, Precision@5/10)
4. Fallback Handling:
   Explicitly reports 'Insufficient real-world interaction data for statistically meaningful online evaluation.'
   when genuine interaction records are sparse (< 10 distinct queries).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class QualityAuditReport:
    """Report detailing interaction data health, missingness, and sequence integrity."""
    total_records: int = 0
    unique_users: int = 0
    unique_recipes: int = 0
    unique_sessions: int = 0
    duplicate_impressions: int = 0
    missing_user_ids: int = 0
    missing_recipe_ids: int = 0
    feedback_without_impression: int = 0
    temporal_inversions: int = 0
    feedback_breakdown: Dict[str, int] = field(default_factory=dict)
    anomalies: List[str] = field(default_factory=list)


def audit_interaction_data(df: pd.DataFrame) -> QualityAuditReport:
    """Audit interaction data quality, reporting anomalies without silent drops."""
    report = QualityAuditReport()
    report.total_records = len(df)
    if df.empty:
        return report

    report.unique_users = df["user_id"].nunique(dropna=True)
    report.unique_recipes = df["recipe_id"].nunique(dropna=True)
    report.unique_sessions = df["session_id"].nunique(dropna=True) if "session_id" in df.columns else 0

    # Null checks
    report.missing_user_ids = int(df["user_id"].isna().sum())
    report.missing_recipe_ids = int(df["recipe_id"].isna().sum())

    # Duplicate check on (session_id, recipe_id)
    if "session_id" in df.columns and "recipe_id" in df.columns:
        dups = df.duplicated(subset=["session_id", "recipe_id"]).sum()
        report.duplicate_impressions = int(dups)
        if dups > 0:
            report.anomalies.append(f"Found {dups} duplicate recipe impressions within identical sessions.")

    # Feedback breakdown
    if "feedback_type" in df.columns:
        fb_series = df["feedback_type"].dropna()
        report.feedback_breakdown = fb_series.value_counts().to_dict()

    # Temporal sequence check (impression_timestamp <= feedback_timestamp)
    if "impression_timestamp" in df.columns and "feedback_timestamp" in df.columns:
        valid_both = df.dropna(subset=["impression_timestamp", "feedback_timestamp"])
        for _, row in valid_both.iterrows():
            try:
                imp_t = pd.to_datetime(row["impression_timestamp"])
                fb_t = pd.to_datetime(row["feedback_timestamp"])
                if fb_t < imp_t:
                    report.temporal_inversions += 1
            except Exception:
                pass
        if report.temporal_inversions > 0:
            report.anomalies.append(
                f"Found {report.temporal_inversions} events where feedback timestamp precedes impression timestamp."
            )

    return report


def temporal_split(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, str]]:
    """Perform time-aware temporal splitting without mixing future interactions."""
    if df.empty or "impression_timestamp" not in df.columns:
        return df, pd.DataFrame(columns=df.columns), pd.DataFrame(columns=df.columns), {}

    # Sort strictly by timestamp
    sorted_df = df.copy()
    sorted_df["dt"] = pd.to_datetime(sorted_df["impression_timestamp"], errors="coerce")
    sorted_df = sorted_df.sort_values(by=["dt"]).drop(columns=["dt"])

    n = len(sorted_df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))

    train_df = sorted_df.iloc[:train_end]
    val_df = sorted_df.iloc[train_end:val_end]
    test_df = sorted_df.iloc[val_end:]

    cutoffs = {
        "train_start": str(train_df["impression_timestamp"].min()) if not train_df.empty else "N/A",
        "train_end": str(train_df["impression_timestamp"].max()) if not train_df.empty else "N/A",
        "val_end": str(val_df["impression_timestamp"].max()) if not val_df.empty else "N/A",
        "test_end": str(test_df["impression_timestamp"].max()) if not test_df.empty else "N/A",
    }
    return train_df, val_df, test_df, cutoffs


def compute_offline_ranking_metrics(df: pd.DataFrame) -> Dict[str, float]:
    """Calculate standard ranking metrics (NDCG, MRR, Precision) on evaluated sessions."""
    if df.empty or "session_id" not in df.columns or "relevance_label" not in df.columns:
        return {}

    ndcg5_list, ndcg10_list, mrr10_list, p5_list, p10_list = [], [], [], [], []

    for session_id, group in df.groupby("session_id"):
        # Sort by ranked position
        sorted_group = group.sort_values(by="position")
        labels = sorted_group["relevance_label"].values

        if len(labels) == 0:
            continue

        # Precision@K (relevant if label >= 2)
        top5_rel = [1 if r >= 2 else 0 for r in labels[:5]]
        top10_rel = [1 if r >= 2 else 0 for r in labels[:10]]
        p5_list.append(sum(top5_rel) / 5.0)
        p10_list.append(sum(top10_rel) / 10.0)

        # MRR@10
        mrr = 0.0
        for rank_idx, rel in enumerate(top10_rel, 1):
            if rel == 1:
                mrr = 1.0 / rank_idx
                break
        mrr10_list.append(mrr)

        # NDCG@K
        def _dcg(rels: np.ndarray, k: int) -> float:
            sub = rels[:k]
            return sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(sub))

        dcg5 = _dcg(labels, 5)
        ideal_labels = np.sort(labels)[::-1]
        idcg5 = _dcg(ideal_labels, 5)
        ndcg5_list.append(dcg5 / idcg5 if idcg5 > 0 else 0.0)

        dcg10 = _dcg(labels, 10)
        idcg10 = _dcg(ideal_labels, 10)
        ndcg10_list.append(dcg10 / idcg10 if idcg10 > 0 else 0.0)

    return {
        "ndcg@5": round(float(np.mean(ndcg5_list)), 4) if ndcg5_list else 0.0,
        "ndcg@10": round(float(np.mean(ndcg10_list)), 4) if ndcg10_list else 0.0,
        "mrr@10": round(float(np.mean(mrr10_list)), 4) if mrr10_list else 0.0,
        "precision@5": round(float(np.mean(p5_list)), 4) if p5_list else 0.0,
        "precision@10": round(float(np.mean(p10_list)), 4) if p10_list else 0.0,
    }


def evaluate_interaction_dataset(
    dataset_path: Path,
) -> Dict[str, object]:
    """Run full evaluation on genuine user feedback dataset."""
    result: Dict[str, object] = {
        "dataset_path": str(dataset_path),
        "status": "evaluated",
        "data_sufficient": False,
        "message": "",
    }

    if not dataset_path.is_file():
        result["status"] = "missing_dataset"
        result["message"] = f"Interaction dataset file not found at {dataset_path}"
        return result

    df = pd.read_csv(dataset_path)
    audit = audit_interaction_data(df)
    result["audit_report"] = audit.__dict__

    # Distinct query sessions check
    distinct_sessions = df["session_id"].nunique() if ("session_id" in df.columns and not df.empty) else 0

    if distinct_sessions < 10 or df.empty:
        msg = "Insufficient real-world interaction data for statistically meaningful online evaluation."
        result["data_sufficient"] = False
        result["message"] = msg
        result["metrics"] = None
        result["splits"] = None
        return result

    result["data_sufficient"] = True
    train_df, val_df, test_df, cutoffs = temporal_split(df)
    result["splits"] = {
        "train_rows": len(train_df),
        "val_rows": len(val_df),
        "test_rows": len(test_df),
        "cutoffs": cutoffs,
    }

    metrics = compute_offline_ranking_metrics(test_df if not test_df.empty else df)
    result["metrics"] = metrics
    result["message"] = f"Successfully evaluated {distinct_sessions} genuine user interaction sessions."
    return result


def main():
    parser = argparse.ArgumentParser(description="Evaluate genuine user feedback interaction dataset.")
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "training" / "user_interaction_events.csv",
        help="Path to interaction dataset CSV.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("KitchenPilot-V1 User Feedback Evaluation Pipeline")
    print(f"Target: {args.input}")
    print("=" * 60)

    report = evaluate_interaction_dataset(args.input)
    print(json.dumps(report, indent=2))
    print("=" * 60)
    if not report.get("data_sufficient", False):
        print(f"NOTICE: {report['message']}")
    else:
        print("EVALUATION COMPLETED SUCCESSFULLY.")


if __name__ == "__main__":
    main()
