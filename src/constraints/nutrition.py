"""Nutrition Constraint Enforcement Subsystem for KitchenPilot-V1.

Applies strict hard boundaries for calories, protein, carbs, fat, and fiber
using authoritative per-serving profiles. Missing values are never silently
treated as zero.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.constraints.models import NutritionConstraints

logger = logging.getLogger("kitchenpilot.constraints.nutrition")

RECIPE_NUTRITION_PATH = Path("data/processed/recipe_nutrition.csv")


class NutritionConstraintEvaluator:
    """Evaluates hard nutritional limits (calories, macros) on per-serving basis."""

    def __init__(self, recipe_nutrition_path: Path = RECIPE_NUTRITION_PATH) -> None:
        self.recipe_nutrition_path = recipe_nutrition_path
        self._nutrition_data: Dict[str, Dict[str, Optional[float]]] = {}
        self._load_nutrition_data()

    def _load_nutrition_data(self) -> None:
        """Load and cache per-serving nutrition values."""
        if not self.recipe_nutrition_path.is_file():
            logger.warning("Nutrition dataset missing: %s", self.recipe_nutrition_path)
            return

        df = pd.read_csv(self.recipe_nutrition_path, low_memory=False)
        for _, row in df.iterrows():
            rid = str(row["recipe_id"]).strip()
            self._nutrition_data[rid] = {
                "calories": float(row["per_serving_calories_kcal"]) if pd.notna(row.get("per_serving_calories_kcal")) else None,
                "protein": float(row["per_serving_protein_g"]) if pd.notna(row.get("per_serving_protein_g")) else None,
                "carbs": float(row["per_serving_carbs_g"]) if pd.notna(row.get("per_serving_carbs_g")) else None,
                "fat": float(row["per_serving_fat_g"]) if pd.notna(row.get("per_serving_fat_g")) else None,
                "fiber": float(row["per_serving_fiber_g"]) if pd.notna(row.get("per_serving_fiber_g")) else None,
                "quality": str(row.get("nutrition_quality", "PARTIAL")).strip(),
            }

    def evaluate_nutrition_constraints(
        self,
        recipe_id: str,
        constraints: NutritionConstraints,
    ) -> Tuple[bool, List[str], List[str], Dict[str, Any]]:
        """Evaluate hard nutritional limits.

        Returns:
            (passed, hard_failures, unknown_constraints, nutrition_summary)
        """
        hard_failures: List[str] = []
        unknown_constraints: List[str] = []

        nut = self._nutrition_data.get(recipe_id)
        if not nut:
            if constraints.has_constraints():
                hard_failures.append("Nutrition record missing: cannot verify nutritional limits.")
            return False, hard_failures, ["all_nutrition_unknown"], {}

        cal = nut["calories"]
        pro = nut["protein"]
        carbs = nut["carbs"]
        fat = nut["fat"]
        fib = nut["fiber"]

        # Helper to check boundary
        def check_limit(
            val: Optional[float],
            limit: Optional[float],
            is_max: bool,
            nutrient_name: str,
            unit: str,
        ) -> None:
            if limit is None:
                return
            if val is None:
                unknown_constraints.append(f"{nutrient_name}_unknown")
                hard_failures.append(f"Cannot verify {nutrient_name}: data unavailable.")
                return

            if is_max and val > limit:
                hard_failures.append(
                    f"{nutrient_name.title()} ({val:.1f}{unit}) exceeds maximum limit ({limit:.1f}{unit})."
                )
            elif not is_max and val < limit:
                hard_failures.append(
                    f"{nutrient_name.title()} ({val:.1f}{unit}) is below minimum requirement ({limit:.1f}{unit})."
                )

        # Calories
        check_limit(cal, constraints.min_calories, is_max=False, nutrient_name="calories", unit=" kcal")
        check_limit(cal, constraints.max_calories, is_max=True, nutrient_name="calories", unit=" kcal")

        # Protein
        check_limit(pro, constraints.min_protein_g, is_max=False, nutrient_name="protein", unit="g")
        check_limit(pro, constraints.max_protein_g, is_max=True, nutrient_name="protein", unit="g")

        # Carbs
        check_limit(carbs, constraints.min_carbs_g, is_max=False, nutrient_name="carbohydrates", unit="g")
        check_limit(carbs, constraints.max_carbs_g, is_max=True, nutrient_name="carbohydrates", unit="g")

        # Fat
        check_limit(fat, constraints.min_fat_g, is_max=False, nutrient_name="fat", unit="g")
        check_limit(fat, constraints.max_fat_g, is_max=True, nutrient_name="fat", unit="g")

        # Fiber
        check_limit(fib, constraints.min_fiber_g, is_max=False, nutrient_name="fiber", unit="g")
        check_limit(fib, constraints.max_fiber_g, is_max=True, nutrient_name="fiber", unit="g")

        passed = len(hard_failures) == 0
        summary = {
            "per_serving_calories": cal,
            "per_serving_protein": pro,
            "per_serving_carbs": carbs,
            "per_serving_fat": fat,
            "per_serving_fiber": fib,
            "nutrition_quality": nut["quality"],
        }
        return passed, hard_failures, unknown_constraints, summary
