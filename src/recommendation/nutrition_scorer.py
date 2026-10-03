"""Nutrition Scorer for KitchenPilot-V1 Recommendation Engine.

Computes normalized nutrition scores and confidence based on frozen recipe nutrition data
and user-specified nutritional targets without modifying or recalculating nutrition values.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from src.recommendation.config import RecommendationConfig


@dataclass
class NutritionGoals:
    """Nutritional goals and constraints specified by the user."""
    calorie_target: Optional[float] = None
    protein_target: Optional[float] = None
    max_calories: Optional[float] = None
    min_protein: Optional[float] = None
    max_fat: Optional[float] = None
    max_carbs: Optional[float] = None
    min_fiber: Optional[float] = None

    def has_goals(self) -> bool:
        """Check if any goal is set."""
        return any(
            v is not None
            for v in [
                self.calorie_target,
                self.protein_target,
                self.max_calories,
                self.min_protein,
                self.max_fat,
                self.max_carbs,
                self.min_fiber,
            ]
        )


@dataclass
class NutritionScoreResult:
    """Score and confidence result for a recipe."""
    nutrition_score: float
    nutrition_confidence: float
    per_serving_calories: Optional[float]
    per_serving_protein: Optional[float]
    nutrition_quality: str


class NutritionScorer:
    """Evaluates how well recipes align with user nutritional goals."""

    def __init__(self, config: Optional[RecommendationConfig] = None) -> None:
        self.config = config or RecommendationConfig()
        self._recipe_nutrition: Dict[str, Dict[str, any]] = {}
        self._load_nutrition_data()

    def _load_nutrition_data(self) -> None:
        """Load frozen recipe nutrition dataset."""
        df = pd.read_csv(self.config.recipe_nutrition_path)
        for _, row in df.iterrows():
            rid = str(row["recipe_id"]).strip()
            self._recipe_nutrition[rid] = {
                "per_serving_calories_kcal": float(row["per_serving_calories_kcal"])
                if pd.notna(row["per_serving_calories_kcal"])
                else None,
                "per_serving_protein_g": float(row["per_serving_protein_g"])
                if pd.notna(row["per_serving_protein_g"])
                else None,
                "per_serving_fat_g": float(row["per_serving_fat_g"])
                if pd.notna(row["per_serving_fat_g"])
                else None,
                "per_serving_carbs_g": float(row["per_serving_carbs_g"])
                if pd.notna(row["per_serving_carbs_g"])
                else None,
                "per_serving_fiber_g": float(row["per_serving_fiber_g"])
                if pd.notna(row["per_serving_fiber_g"])
                else None,
                "nutrition_quality": str(row["nutrition_quality"]).strip()
                if pd.notna(row["nutrition_quality"])
                else "PARTIAL",
                "ingredient_count": int(row["ingredient_count"])
                if pd.notna(row.get("ingredient_count"))
                else 0,
                "calculated_ingredient_count": int(row["calculated_ingredient_count"])
                if pd.notna(row.get("calculated_ingredient_count"))
                else 0,
            }

    def compute_confidence(self, recipe_id: str) -> float:
        """Compute nutrition confidence based on quality status and calculated ingredient coverage."""
        data = self._recipe_nutrition.get(recipe_id)
        if not data:
            return 0.0

        qual = data["nutrition_quality"]
        if qual == "COMPLETE":
            return 1.0
        if qual == "APPROXIMATE":
            return 0.85

        # PARTIAL quality: confidence scales with the fraction of calculated ingredients
        total = data["ingredient_count"]
        calc = data["calculated_ingredient_count"]
        if total > 0:
            coverage = min(1.0, calc / total)
            # PARTIAL confidence maxes out at 0.50
            return round(0.50 * coverage, 3)
        return 0.10

    def score_recipe(
        self,
        recipe_id: str,
        goals: Optional[NutritionGoals] = None,
    ) -> NutritionScoreResult:
        """Score a recipe against specified nutrition goals."""
        data = self._recipe_nutrition.get(recipe_id)
        if not data:
            return NutritionScoreResult(
                nutrition_score=0.0,
                nutrition_confidence=0.0,
                per_serving_calories=None,
                per_serving_protein=None,
                nutrition_quality="UNAVAILABLE",
            )

        confidence = self.compute_confidence(recipe_id)
        cal = data["per_serving_calories_kcal"]
        prot = data["per_serving_protein_g"]
        fat = data["per_serving_fat_g"]
        carbs = data["per_serving_carbs_g"]
        fiber = data["per_serving_fiber_g"]
        qual = data["nutrition_quality"]

        # If no goals provided, return neutral score 1.0 with computed confidence
        if goals is None or not goals.has_goals():
            return NutritionScoreResult(
                nutrition_score=1.0,
                nutrition_confidence=confidence,
                per_serving_calories=cal,
                per_serving_protein=prot,
                nutrition_quality=qual,
            )

        # If calories or nutrition is completely unavailable, score is 0.0 with 0 confidence
        if cal is None:
            return NutritionScoreResult(
                nutrition_score=0.0,
                nutrition_confidence=0.0,
                per_serving_calories=None,
                per_serving_protein=None,
                nutrition_quality=qual,
            )

        sub_scores = []

        # 1. Calorie Target
        if goals.calorie_target is not None and goals.calorie_target > 0:
            diff = abs(cal - goals.calorie_target)
            # Full score at target; 0 score if diff >= target
            sub_scores.append(max(0.0, 1.0 - (diff / goals.calorie_target)))

        # 2. Protein Target
        if goals.protein_target is not None and goals.protein_target > 0:
            actual_prot = prot if prot is not None else 0.0
            sub_scores.append(min(1.0, max(0.0, actual_prot / goals.protein_target)))

        # 3. Max Calories
        if goals.max_calories is not None and goals.max_calories > 0:
            if cal <= goals.max_calories:
                sub_scores.append(1.0)
            else:
                excess = cal - goals.max_calories
                sub_scores.append(max(0.0, 1.0 - (excess / goals.max_calories)))

        # 4. Min Protein
        if goals.min_protein is not None and goals.min_protein > 0:
            actual_prot = prot if prot is not None else 0.0
            if actual_prot >= goals.min_protein:
                sub_scores.append(1.0)
            else:
                sub_scores.append(max(0.0, actual_prot / goals.min_protein))

        # 5. Max Fat
        if goals.max_fat is not None and goals.max_fat > 0:
            actual_fat = fat if fat is not None else 0.0
            if actual_fat <= goals.max_fat:
                sub_scores.append(1.0)
            else:
                excess = actual_fat - goals.max_fat
                sub_scores.append(max(0.0, 1.0 - (excess / goals.max_fat)))

        # 6. Max Carbs
        if goals.max_carbs is not None and goals.max_carbs > 0:
            actual_carbs = carbs if carbs is not None else 0.0
            if actual_carbs <= goals.max_carbs:
                sub_scores.append(1.0)
            else:
                excess = actual_carbs - goals.max_carbs
                sub_scores.append(max(0.0, 1.0 - (excess / goals.max_carbs)))

        # 7. Min Fiber
        if goals.min_fiber is not None and goals.min_fiber > 0:
            actual_fiber = fiber if fiber is not None else 0.0
            if actual_fiber >= goals.min_fiber:
                sub_scores.append(1.0)
            else:
                sub_scores.append(max(0.0, actual_fiber / goals.min_fiber))

        final_score = float(sum(sub_scores) / len(sub_scores)) if sub_scores else 1.0
        final_score = round(min(1.0, max(0.0, final_score)), 4)

        return NutritionScoreResult(
            nutrition_score=final_score,
            nutrition_confidence=confidence,
            per_serving_calories=cal,
            per_serving_protein=prot,
            nutrition_quality=qual,
        )
