"""Recommendation audit logging for interaction tracking and future training datasets."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from src.personalization.models import RecommendationHistoryModel

logger = logging.getLogger("kitchenpilot.personalization.history")


def generate_session_id() -> str:
    """Generate a unique recommendation session/request identifier."""
    return f"sess_{uuid.uuid4().hex[:16]}"


def log_recommendation_events(
    db: Session,
    user_id: Optional[int],
    session_id: str,
    ranked_candidates: List[Any],
    ranking_method: str,
    model_version: str,
    personalization_applied: bool,
    context_metadata: Optional[Dict[str, Any]] = None,
) -> List[RecommendationHistoryModel]:
    """Audit log recommendation events for an authenticated or anonymous request.
    
    Returns created RecommendationHistoryModel instances.
    """
    if not ranked_candidates:
        return []

    events = []
    meta = context_metadata or {}
    now = datetime.now(timezone.utc)

    try:
        for idx, cand in enumerate(ranked_candidates, start=1):
            rid = str(getattr(cand, "recipe_id", "")).strip()
            base_score = float(getattr(cand, "hybrid_score", 0.0) or 0.0)
            pers_score = float(getattr(cand, "personalization_score", 0.0) or 0.0)
            final_score = float(getattr(cand, "final_score", base_score) or base_score)

            event = RecommendationHistoryModel(
                user_id=user_id,
                session_id=session_id,
                recipe_id=rid,
                position=idx,
                ranking_method=ranking_method,
                model_version=model_version,
                personalization_applied=personalization_applied,
                base_score=round(base_score, 6),
                personalization_score=round(pers_score, 6),
                final_score=round(final_score, 6),
                context_metadata=meta,
                created_at=now,
            )
            db.add(event)
            events.append(event)

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to commit recommendation history events: %s", exc)

    return events
