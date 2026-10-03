"""Deterministic Explainability Module for KitchenPilot-V1 Recommendation Engine.

Generates transparent, template-based natural language explanations for every recommendation
without using external LLMs or non-deterministic generators.
"""

from __future__ import annotations

from typing import List, Optional

from src.recommendation.hybrid_ranker import ScoredCandidate


class ExplanationGenerator:
    """Generates deterministic, template-based explanations for recipe recommendations."""

    @staticmethod
    def generate_explanation(
        candidate: ScoredCandidate,
        query_recipe_name: Optional[str] = None,
        has_available_ingredients: bool = False,
        total_available: int = 0,
        calorie_target: Optional[float] = None,
        protein_target: Optional[float] = None,
    ) -> str:
        """Construct a natural language explanation describing why the candidate was recommended."""
        reasons: List[str] = []

        # 1. Ingredient matching clause
        if has_available_ingredients and total_available > 0:
            m_count = len(candidate.matched_ingredients)
            if m_count == total_available:
                reasons.append(f"matches all {total_available} of your available ingredients")
            elif m_count > 0:
                reasons.append(f"matches {m_count} of your {total_available} available ingredients")
            else:
                reasons.append("offers a creative recipe alternative")
        elif candidate.matched_ingredients:
            top_ings = candidate.matched_ingredients[:3]
            reasons.append(f"features key ingredients ({', '.join(top_ings)})")

        # 2. Recipe similarity clause
        if query_recipe_name:
            if candidate.similarity_score >= 0.60:
                sim_desc = "very high culinary profile similarity"
            elif candidate.similarity_score >= 0.35:
                sim_desc = "high flavor and preparation similarity"
            elif candidate.similarity_score >= 0.15:
                sim_desc = "complementary culinary style"
            else:
                sim_desc = "related flavor notes"
            reasons.append(f"has {sim_desc} to '{query_recipe_name}'")

        # 3. Nutrition target clause
        if calorie_target is not None and candidate.per_serving_calories is not None:
            diff = abs(candidate.per_serving_calories - calorie_target)
            if diff <= 75:
                reasons.append(f"closely fits your target of {calorie_target:.0f} kcal (~{candidate.per_serving_calories:.0f} kcal/serving)")
            else:
                reasons.append(f"provides ~{candidate.per_serving_calories:.0f} kcal/serving toward your goal")
        elif protein_target is not None and candidate.per_serving_protein is not None:
            if candidate.per_serving_protein >= protein_target:
                reasons.append(f"meets your protein goal with {candidate.per_serving_protein:.1f}g protein/serving")
            else:
                reasons.append(f"supplies {candidate.per_serving_protein:.1f}g protein/serving")
        elif candidate.nutrition_confidence >= 0.85 and candidate.per_serving_calories is not None:
            reasons.append(f"offers verified nutrition ({candidate.per_serving_calories:.0f} kcal/serving)")

        # 4. Dietary/Preference clause
        if candidate.matched_preferences:
            pref_str = ", ".join(candidate.matched_preferences[:2])
            reasons.append(f"satisfies your {pref_str} preferences")

        if not reasons:
            return f"Recommended with an overall hybrid match score of {candidate.hybrid_score:.2f}."

        if len(reasons) == 1:
            joined = reasons[0]
        elif len(reasons) == 2:
            joined = f"{reasons[0]} and {reasons[1]}"
        else:
            joined = f"{', '.join(reasons[:-1])}, and {reasons[-1]}"

        return f"Recommended because it {joined}."
