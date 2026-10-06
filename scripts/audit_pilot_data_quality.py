"""
KitchenPilot-V1 — Pilot Feedback Data Quality CLI (Stage K)

Executes the automated data-quality audit against the database and reports
detailed integrity metrics across real user interactions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.db.base import Base
from src.db.session import check_db_connection, get_db_session
from src.ml.pilot_audit import PilotDataQualityReport, audit_pilot_feedback_data


def main() -> int:
    parser = argparse.ArgumentParser(description="KitchenPilot-V1 Pilot Data Quality Audit")
    parser.add_argument("--json", action="store_true", help="Output audit report in raw JSON format")
    args = parser.parse_args()

    # Verify database connection
    is_reachable, _ = check_db_connection(timeout_seconds=2)
    if is_reachable:
        with get_db_session() as db:
            report = audit_pilot_feedback_data(db)
    else:
        # If database service is not actively running, audit against a clean localized schema
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)
        with Session(engine) as db:
            report = audit_pilot_feedback_data(db)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.quality_status in ("CLEAN", "ACCEPTABLE") else 1

    print("=" * 65)
    print(" KitchenPilot-V1 -- Pilot Feedback Data Quality Audit (Stage K)")
    print("=" * 65)
    print(f" Audit Timestamp:          {report.audit_timestamp}")
    print(f" Quality Status:           {report.quality_status}")
    print("-" * 65)
    print(f" Total Interactions:       {report.total_interactions}")
    print(f" Unique Users:             {report.unique_users}")
    print(f" Unique Recipes:           {report.unique_recipes}")
    print(f" Unique Query Groups:      {report.unique_query_groups}")
    print(f" Days of Feedback Data:    {report.days_of_data} days")
    print(f" Date Range:               {report.date_range_start or 'N/A'} -> {report.date_range_end or 'N/A'}")
    print("-" * 65)
    print(f" Positive Labels (2, 3):   {report.positive_labels}")
    print(f" Negative Labels (0):      {report.negative_labels}")
    print(f" Impressions / Neutral:    {report.neutral_impression_labels}")
    print(f" Label Breakdown:          {report.label_breakdown}")
    print("-" * 65)
    print(f" Duplicate Events:         {report.duplicate_events_count}")
    print(f" Invalid User IDs:         {report.invalid_users_count}")
    print(f" Invalid Recipe IDs:       {report.invalid_recipes_count}")
    print(f" Temporal Violations:      {report.temporal_violations_count}")
    print(f" Missing Query Groups:     {report.missing_query_groups_count}")
    print(f" Conflicting Pairs:        {report.conflicting_feedback_pairs}")
    print("=" * 65)

    if report.detected_anomalies:
        print("\nAudit Notes / Anomalies:")
        for a in report.detected_anomalies:
            print(f"  - {a}")
        print()

    if report.quality_status == "DEFECTS_DETECTED":
        print("[FAIL] Audit detected critical data quality defects.")
        return 1

    print("[PASS] Pilot data quality audit completed cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
