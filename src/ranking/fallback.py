"""Adaptive ranking dispatcher with mandatory HybridRanker fallback for Stage F.

Ensures the system remains resilient and production-ready:
1. Primary: XGBoost ranker (when enabled and model healthy)
2. Mandatory Fallback: Existing deterministic HybridRanker
3. Transparent telemetry: Records which ranker produced the recommendation
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.ranking.features import RankingContext
from src.ranking.xgboost_ranker import XGBoostRanker
from src.recommendation.hybrid_ranker import HybridRanker, ScoredCandidate

logger = logging.getLogger("kitchenpilot.ranking.dispatcher")


class RankingDispatcher:
    """Orchestrates ranking execution with automatic fallback to HybridRanker."""

    def __init__(
        self,
        xgboost_ranker: Optional[XGBoostRanker] = None,
        hybrid_ranker: Optional[HybridRanker] = None,
        enabled: bool = False,
    ) -> None:
        self.xgboost_ranker = xgboost_ranker or XGBoostRanker()
        self.hybrid_ranker = hybrid_ranker or HybridRanker()
        self.enabled = enabled
        self.last_ranker_used: str = "hybrid"

    def rank_candidates(
        self,
        candidates: List[ScoredCandidate],
        context: Optional[RankingContext] = None,
        top_k: int = 10,
    ) -> List[ScoredCandidate]:
        """Rank eligible candidates using XGBoost when enabled or fallback to HybridRanker."""
        if not candidates:
            return []

        if not self.enabled or context is None:
            self.last_ranker_used = "hybrid"
            return self.hybrid_ranker.rank_candidates(candidates, top_k=top_k)

        # Attempt XGBoost ranking with quality guards
        try:
            candidate_ids = [c.recipe_id for c in candidates]
            ranked_pairs = self.xgboost_ranker.rank(candidate_ids, context, top_k=top_k)

            # Map back to ScoredCandidate objects in predicted rank order
            cand_map = {c.recipe_id: c for c in candidates}
            ranked_candidates: List[ScoredCandidate] = []
            for rid, score in ranked_pairs:
                cand = cand_map[rid]
                # Update hybrid_score with calibrated XGBoost score
                cand.hybrid_score = round(float(score), 4)
                ranked_candidates.append(cand)

            self.last_ranker_used = "xgboost"
            return ranked_candidates

        except Exception as e:
            logger.warning(
                "XGBoost ranking failed (%s). Executing mandatory fallback to HybridRanker.",
                e,
                exc_info=True,
            )
            self.last_ranker_used = "hybrid"
            return self.hybrid_ranker.rank_candidates(candidates, top_k=top_k)
