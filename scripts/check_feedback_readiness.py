"""KitchenPilot-V1 — Feedback Readiness Gate Verification Script (Stage J).

Audits genuine real-world user interactions in the database against the
authoritative Stage I ML Lifecycle Data Sufficiency Thresholds:
- MIN_INTERACTIONS = 200
- MIN_USERS = 20
- MIN_RECIPES = 50
- MIN_QUERY_GROUPS = 30
- MIN_POSITIVE_LABELS = 40
- MIN_NEGATIVE_LABELS = 10
- MIN_DAYS_OF_DATA = 7 days

Safety Invariant:
DO NOT fabricate, synthesize, bootstrap, or manually manufacture feedback data.
If thresholds are not met, reports status: INSUFFICIENT_DATA and safely halts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.session import check_db_connection, get_db_session
from src.ml.config import (
    MIN_DAYS_OF_DATA,
    MIN_INTERACTIONS,
    MIN_NEGATIVE_LABELS,
    MIN_POSITIVE_LABELS,
    MIN_QUERY_GROUPS,
    MIN_RECIPES,
    MIN_USERS,
)
from src.ml.data_quality import check_data_sufficiency
from scripts.export_interaction_dataset import export_interaction_dataset
import pandas as pd


def run_readiness_audit(db_url: str = None) -> dict:
    print("=" * 65)
    print("KitchenPilot-V1 — Real Feedback Readiness Gate Audit (Stage J)")
    print(f"Project root: {PROJECT_ROOT}")
    print("=" * 65)

    is_db_reachable, db_err = check_db_connection(db_url=db_url, timeout_seconds=2)
    if is_db_reachable:
        with get_db_session() as session:
            df = export_interaction_dataset(output_path=None, db=session)
    else:
        # If database is offline or not provisioned, check if a local exported dataset exists
        export_file = PROJECT_ROOT / "data" / "training" / "user_interaction_events.csv"
        if export_file.is_file():
            df = pd.read_csv(export_file)
        else:
            df = pd.DataFrame(columns=[
                "session_id", "user_id", "recipe_id", "position", "ranking_method",
                "model_version", "base_score", "personalization_score", "final_score",
                "impression_timestamp", "feedback_type", "rating", "feedback_timestamp",
                "relevance_label",
            ])


    res = check_data_sufficiency(df)

    print("\n--- Current Data Sufficiency Gate Status ---")
    print(f"Status: {res.status}")
    print(f"Is Sufficient for ML Retraining: {res.is_sufficient}")
    print("\nParameter Threshold Comparison:")
    print(f"  Total Interactions : {res.total_interactions:>5} / {MIN_INTERACTIONS} required")
    print(f"  Unique Users       : {res.unique_users:>5} / {MIN_USERS} required")
    print(f"  Unique Recipes     : {res.unique_recipes:>5} / {MIN_RECIPES} required")
    print(f"  Unique Queries     : {res.unique_queries:>5} / {MIN_QUERY_GROUPS} required")
    print(f"  Positive Labels    : {res.positive_labels:>5} / {MIN_POSITIVE_LABELS} required")
    print(f"  Negative Labels    : {res.negative_labels:>5} / {MIN_NEGATIVE_LABELS} required")
    print(f"  Days of Data       : {res.days_of_data:>5.1f} / {MIN_DAYS_OF_DATA:.1f} days required")

    if res.violations:
        print("\nBlocking Gate Violations:")
        for v in res.violations:
            print(f"  [GATE_BLOCKED] {v}")

    print("\nGoverning ML Safety Policy:")
    print("  - Real-world interaction data collection is currently in progress via Controlled Pilot.")
    print("  - Models cannot be retrained, compared, or promoted until all sufficiency gates pass.")
    print("  - Current active production model remains frozen: xgb_ranker_v0.1.0.")
    print("=" * 65)

    return {
        "status": res.status,
        "is_sufficient": res.is_sufficient,
        "metrics": {
            "total_interactions": res.total_interactions,
            "min_interactions_required": MIN_INTERACTIONS,
            "unique_users": res.unique_users,
            "min_users_required": MIN_USERS,
            "unique_recipes": res.unique_recipes,
            "min_recipes_required": MIN_RECIPES,
            "unique_queries": res.unique_queries,
            "min_queries_required": MIN_QUERY_GROUPS,
            "positive_labels": res.positive_labels,
            "min_positive_labels_required": MIN_POSITIVE_LABELS,
            "negative_labels": res.negative_labels,
            "min_negative_labels_required": MIN_NEGATIVE_LABELS,
            "days_of_data": res.days_of_data,
            "min_days_required": MIN_DAYS_OF_DATA,
        },
        "violations": res.violations,
        "active_production_model": "xgb_ranker_v0.1.0",
    }


def main():
    parser = argparse.ArgumentParser(description="Audit feedback sufficiency against Stage I ML gates.")
    parser.add_argument("--json", action="store_true", help="Output summary as JSON")
    args = parser.parse_args()

    result = run_readiness_audit()
    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
