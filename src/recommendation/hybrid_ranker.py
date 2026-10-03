"""Hybrid Ranker for KitchenPilot-V1 Recommendation Engine.

Combines similarity, ingredient matching, nutrition scoring, and preference compatibility
into a normalized [0, 1] hybrid score using configurable weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.recommendation.config import HybridWeights, RecommendationConfig


@dataclass
class ScoredCandidate:
    """A fully scored recipe candidate ready for ranking and explanation."""
    recipe_id: str
    recipe_name: str
    similarity_score: float
    ingredient_match_score: float
    nutrition_score: float
    preference_score: float
    nutrition_confidence: float
    hybrid_score: float = 0.0
    matched_ingredients: List[str] = field(default_factory=list)
    missing_ingredients: List[str] = field(default_factory=list)
    matched_preferences: List[str] = field(default_factory=list)
    per_serving_calories: Optional[float] = None
    per_serving_protein: Optional[float] = None
    explanation: str = ""


class HybridRanker:
    """Computes hybrid recommendation scores and sorts candidates deterministically."""

    def __init__(
        self,
        config: Optional[RecommendationConfig] = None,
        weights: Optional[HybridWeights] = None,
    ) -> None:
        self.config = config or RecommendationConfig()
        self.weights = weights or self.config.weights
        self.weights.validate()

    def calculate_hybrid_score(
        self,
        similarity_score: float,
        ingredient_score: float,
        nutrition_score: float,
        preference_score: float,
    ) -> float:
        """Calculate weighted hybrid score bounded strictly in [0.0, 1.0]."""
        w = self.weights
        # Clamp inputs to [0, 1]
        sim = min(1.0, max(0.0, similarity_score))
        ing = min(1.0, max(0.0, ingredient_score))
        nut = min(1.0, max(0.0, nutrition_score))
        pref = min(1.0, max(0.0, preference_score))

        score = (
            w.similarity * sim
            + w.ingredient * ing
            + w.nutrition * nut
            + w.preference * pref
        )
        return float(round(min(1.0, max(0.0, score)), 4))

    def rank_candidates(
        self,
        candidates: List[ScoredCandidate],
        top_k: int = 10,
    ) -> List[ScoredCandidate]:
        """Rank candidates deterministically descending by hybrid_score."""
        for c in candidates:
            c.hybrid_score = self.calculate_hybrid_score(
                similarity_score=c.similarity_score,
                ingredient_score=c.ingredient_match_score,
                nutrition_score=c.nutrition_score,
                preference_score=c.preference_score,
            )

        # Deterministic sort: -hybrid_score, -similarity_score, -ingredient_match_score, recipe_id
        sorted_candidates = sorted(
            candidates,
            key=lambda x: (-x.hybrid_score, -x.similarity_score, -x.ingredient_match_score, x.recipe_id),
        )

        return sorted_candidates[:top_k]
