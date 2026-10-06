"""Export genuine user interaction and recommendation event history for future ranking model retraining.

KitchenPilot-V1 — Stage G Foundation for Learning-to-Rank Supervision.
This script extracts historical impression events joined with explicit user feedback
to produce query-grouped interaction datasets without synthetic fabrication.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.session import get_db_session
from src.personalization.models import RecommendationHistoryModel, UserFeedbackModel


def export_interaction_dataset(
    output_path: Optional[Path] = None,
    db: Optional[Session] = None,
) -> pd.DataFrame:
    """Export recommendation events joined with explicit feedback for future model training."""
    target_path = output_path or (PROJECT_ROOT / "data" / "training" / "user_interaction_events.csv")

    def _query(session: Session) -> pd.DataFrame:
        stmt = (
            select(
                RecommendationHistoryModel.session_id,
                RecommendationHistoryModel.user_id,
                RecommendationHistoryModel.recipe_id,
                RecommendationHistoryModel.position,
                RecommendationHistoryModel.ranking_method,
                RecommendationHistoryModel.model_version,
                RecommendationHistoryModel.base_score,
                RecommendationHistoryModel.personalization_score,
                RecommendationHistoryModel.final_score,
                RecommendationHistoryModel.created_at.label("impression_timestamp"),
                UserFeedbackModel.feedback_type,
                UserFeedbackModel.rating,
                UserFeedbackModel.created_at.label("feedback_timestamp"),
            )
            .outerjoin(
                UserFeedbackModel,
                (RecommendationHistoryModel.user_id == UserFeedbackModel.user_id)
                & (RecommendationHistoryModel.recipe_id == UserFeedbackModel.recipe_id),
            )
            .order_by(RecommendationHistoryModel.session_id, RecommendationHistoryModel.position)
        )
        rows = session.execute(stmt).all()
        if not rows:
            cols = [
                "session_id", "user_id", "recipe_id", "position", "ranking_method",
                "model_version", "base_score", "personalization_score", "final_score",
                "impression_timestamp", "feedback_type", "rating", "feedback_timestamp",
                "relevance_label",
            ]
            return pd.DataFrame(columns=cols)

        data = []
        for r in rows:
            # Map explicit feedback to future ground-truth relevance grade
            # COOKED: 3 (highest engagement)
            # SAVE: 2 (high engagement)
            # LIKE: 2 (positive)
            # DISLIKE: 0 (negative)
            # HIDE: 0 (strong negative)
            # None: 1 (examined / baseline impression)
            fb = r.feedback_type
            if fb == "COOKED":
                rel = 3
            elif fb in ("SAVE", "LIKE"):
                rel = 2
            elif fb in ("DISLIKE", "HIDE"):
                rel = 0
            else:
                rel = 1  # Unlabeled impression

            data.append({
                "session_id": r.session_id,
                "user_id": r.user_id,
                "recipe_id": r.recipe_id,
                "position": r.position,
                "ranking_method": r.ranking_method,
                "model_version": r.model_version,
                "base_score": r.base_score,
                "personalization_score": r.personalization_score,
                "final_score": r.final_score,
                "impression_timestamp": r.impression_timestamp.isoformat() if r.impression_timestamp else None,
                "feedback_type": fb,
                "rating": r.rating,
                "feedback_timestamp": r.feedback_timestamp.isoformat() if r.feedback_timestamp else None,
                "relevance_label": rel,
            })

        df = pd.DataFrame(data)
        try:
            from src.ml.labels import resolve_conflicting_interactions
            df = resolve_conflicting_interactions(df)
        except Exception:
            pass
        target_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(target_path, index=False)
        return df

    if db is not None:
        return _query(db)
    else:
        with get_db_session() as session:
            return _query(session)


def main():
    parser = argparse.ArgumentParser(description="Export recommendation and feedback interactions.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "training" / "user_interaction_events.csv",
        help="Path to output CSV file.",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Optional database connection URL (e.g., sqlite:///file.db).",
    )
    args = parser.parse_args()

    from src.db.config import get_database_url
    from src.db.session import check_db_connection

    target_url = args.db_url or get_database_url()
    is_live, err = check_db_connection(target_url, timeout_seconds=2)

    if not is_live:
        print(f"[OFFLINE] Database at '{target_url}' is currently unreachable: {err}")
        print("Writing schema template to target path without terminating with failure.")
        cols = [
            "session_id", "user_id", "recipe_id", "position", "ranking_method",
            "model_version", "base_score", "personalization_score", "final_score",
            "impression_timestamp", "feedback_type", "rating", "feedback_timestamp",
            "relevance_label",
        ]
        df = pd.DataFrame(columns=cols)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.output, index=False)
        print(f"Created schema template with {len(cols)} columns at {args.output}")
        return

    print("Exporting user interaction dataset for future offline model retraining...")
    if args.db_url:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        engine = create_engine(args.db_url)
        factory = sessionmaker(bind=engine)
        with factory() as session:
            df = export_interaction_dataset(output_path=args.output, db=session)
    else:
        df = export_interaction_dataset(output_path=args.output)
    print(f"Exported {len(df)} interaction events to {args.output}")


if __name__ == "__main__":
    main()
