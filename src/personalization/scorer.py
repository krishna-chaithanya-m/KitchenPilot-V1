"""Personalization scoring and deterministic reranking engine for KitchenPilot-V1."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.personalization.features import (
    PersonalizationSignals,
    UserPersonalizationContext,
    extract_personalization_signals,
)

logger = logging.getLogger("kitchenpilot.personalization")


class PersonalizationScorer:
    """Computes bounded personalization adjustments and deterministic reranking."""

    def __init__(self, weight: float = 0.20, enabled: bool = True):
        self.weight = max(0.0, min(1.0, float(weight)))
        self.enabled = bool(enabled)

    def compute_adjustment(
        self,
        signals: PersonalizationSignals,
    ) -> Tuple[float, float]:
        """Compute raw personalization score in [-1.0, 1.0] and weighted adjustment.
        
        Returns:
            (raw_score, adjustment)
        """
        if not self.enabled:
            return 0.0, 0.0

        # Positive contribution terms
        pos = (
            0.20 * signals.cuisine_affinity
            + 0.10 * signals.region_affinity
            + 0.10 * signals.meal_type_affinity
            + 0.10 * signals.category_affinity
            + 0.25 * signals.pantry_overlap_ratio
            + 0.15 * min(signals.preferred_ingredient_match_count * 0.1, 0.3)
            + 0.30 * (1.0 if signals.past_liked else 0.0)
            + 0.25 * (1.0 if signals.past_saved else 0.0)
            + 0.20 * (1.0 if signals.past_cooked else 0.0)
            + 0.15 * signals.nutrition_target_alignment
        )

        # Negative penalty terms
        neg = (
            0.40 * signals.disliked_ingredient_penalty
            + 0.50 * (1.0 if signals.past_disliked else 0.0)
            + 1.00 * (1.0 if signals.past_hidden else 0.0)
            + 0.15 * (1.0 if signals.recently_recommended else 0.0)
        )

        raw = pos - neg
        # Strict clipping to [-1.0, 1.0]
        clipped_raw = max(-1.0, min(1.0, raw))
        adjustment = self.weight * clipped_raw

        signals.raw_personalization_score = clipped_raw
        signals.personalization_adjustment = adjustment

        return clipped_raw, adjustment

    def rerank_candidates(
        self,
        candidates: List[Any],
        recipe_metadata_map: Dict[str, Dict[str, Any]],
        context: Optional[UserPersonalizationContext],
        top_k: int = 10,
    ) -> List[Any]:
        """Apply bounded personalization adjustments to candidates and sort deterministically.
        
        Candidates MUST have already passed Stage E hard constraint filtering.
        If context is None or personalization is disabled, candidates retain base ranking.
        """
        if not candidates:
            return []

        if not self.enabled or context is None:
            # Baseline anonymous parity: keep ranking as-is
            for cand in candidates:
                cand.personalization_score = 0.0
                cand.personalization_applied = False
                cand.final_score = getattr(cand, "hybrid_score", 0.0)
            return candidates[:top_k]

        for cand in candidates:
            rid = str(cand.recipe_id).strip()
            meta = recipe_metadata_map.get(rid, {"recipe_id": rid})
            signals = extract_personalization_signals(meta, context)
            raw_score, adj = self.compute_adjustment(signals)

            cand.personalization_score = adj
            cand.personalization_applied = True
            base_score = getattr(cand, "hybrid_score", 0.0)
            cand.final_score = max(0.0, base_score + adj)
            cand.personalization_signals = signals

            # Append personalization reasons to explanation if available
            if signals.reasons and hasattr(cand, "explanation"):
                existing = cand.explanation or ""
                reasons_str = "; ".join(signals.reasons)
                if existing:
                    cand.explanation = f"{existing} | Personalization: {reasons_str}"
                else:
                    cand.explanation = f"Personalization: {reasons_str}"

        # Deterministic 3-tier tie-breaking:
        # 1. final_score descending
        # 2. base_score descending
        # 3. recipe_id ascending
        ranked = sorted(
            candidates,
            key=lambda c: (
                -round(getattr(c, "final_score", 0.0), 6),
                -round(getattr(c, "hybrid_score", 0.0), 6),
                str(c.recipe_id),
            ),
        )

        return ranked[:top_k]
