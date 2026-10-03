"""Nutrient lookup and scaling against normalized CNF 2026 nutrition data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

import pandas as pd


@dataclass(frozen=True)
class NutrientProfile:
    """Nutritional profile for an ingredient or recipe."""

    energy_kcal: float = 0.0
    protein_g: float = 0.0
    fat_g: float = 0.0
    carbs_g: float = 0.0
    fiber_g: float = 0.0
    sugar_g: float = 0.0
    sodium_mg: float = 0.0

    def scale(self, grams: float) -> NutrientProfile:
        """Scale nutrient profile from 100g basis to the specified mass in grams."""
        factor = grams / 100.0
        return NutrientProfile(
            energy_kcal=round(self.energy_kcal * factor, 3),
            protein_g=round(self.protein_g * factor, 3),
            fat_g=round(self.fat_g * factor, 3),
            carbs_g=round(self.carbs_g * factor, 3),
            fiber_g=round(self.fiber_g * factor, 3),
            sugar_g=round(self.sugar_g * factor, 3),
            sodium_mg=round(self.sodium_mg * factor, 3),
        )

    def add(self, other: NutrientProfile) -> NutrientProfile:
        """Sum two nutrient profiles."""
        return NutrientProfile(
            energy_kcal=round(self.energy_kcal + other.energy_kcal, 3),
            protein_g=round(self.protein_g + other.protein_g, 3),
            fat_g=round(self.fat_g + other.fat_g, 3),
            carbs_g=round(self.carbs_g + other.carbs_g, 3),
            fiber_g=round(self.fiber_g + other.fiber_g, 3),
            sugar_g=round(self.sugar_g + other.sugar_g, 3),
            sodium_mg=round(self.sodium_mg + other.sodium_mg, 3),
        )

    def divide(self, divisor: float) -> NutrientProfile:
        """Divide nutrient profile by a divisor (e.g. number of servings)."""
        if divisor <= 0:
            raise ValueError(f"Divisor must be greater than zero, got {divisor}")
        return NutrientProfile(
            energy_kcal=round(self.energy_kcal / divisor, 3),
            protein_g=round(self.protein_g / divisor, 3),
            fat_g=round(self.fat_g / divisor, 3),
            carbs_g=round(self.carbs_g / divisor, 3),
            fiber_g=round(self.fiber_g / divisor, 3),
            sugar_g=round(self.sugar_g / divisor, 3),
            sodium_mg=round(self.sodium_mg / divisor, 3),
        )


# Target core nutrient codes in CNF 2026
CORE_NUTRIENT_IDS = {
    "203": "protein_g",
    "204": "fat_g",
    "205": "carbs_g",
    "208": "energy_kcal",
    "269": "sugar_g",
    "291": "fiber_g",
    "307": "sodium_mg",
}


class NutrientLookup:
    """Fast, pre-indexed in-memory lookup table for core CNF nutrient profiles.

    Architecture:
    - Mode A (offline processing): If data/processed/cnf_2026_nutrition.csv exists locally,
      it may be used for offline processing.
    - Mode B (committed release-safe fallback): If the 297 MB processed file does not exist,
      NutrientLookup automatically falls back to the committed Health Canada raw table
      data/raw/nutrition/cnf_2026/nutrient_amount.csv.
    """

    def __init__(
        self,
        cnf_nutrition_path: Path | str = "data/processed/cnf_2026_nutrition.csv",
        raw_nutrient_path: Path | str = "data/raw/nutrition/cnf_2026/nutrient_amount.csv",
        active_food_codes: Optional[Set[int]] = None,
    ) -> None:
        self.cnf_nutrition_path = Path(cnf_nutrition_path)
        self.raw_nutrient_path = Path(raw_nutrient_path)
        self._profiles_per_100g: Dict[int, NutrientProfile] = {}
        self._load_table(active_food_codes)

    def _load_table(self, active_food_codes: Optional[Set[int]]) -> None:
        """Read and index normalized CNF nutrition profiles on a 100g edible portion basis."""
        if self.cnf_nutrition_path.is_file():
            # Mode A: Load from processed CNF file (offline intermediate)
            usecols = ["source_food_id", "nutrient_id", "nutrient_value"]
            df = pd.read_csv(self.cnf_nutrition_path, usecols=usecols, dtype=str)
            food_col = "source_food_id"
            nutrient_col = "nutrient_id"
            val_col = "nutrient_value"
        elif self.raw_nutrient_path.is_file():
            # Mode B: Load from raw committed CNF nutrient amount table
            usecols = ["Food_Code", "Nutrient_Code", "Nutrient_Amount"]
            df = pd.read_csv(self.raw_nutrient_path, usecols=usecols, dtype=str)
            food_col = "Food_Code"
            nutrient_col = "Nutrient_Code"
            val_col = "Nutrient_Amount"
        else:
            raise FileNotFoundError(
                f"Missing CNF nutrition file: neither {self.cnf_nutrition_path} "
                f"nor {self.raw_nutrient_path} exists."
            )

        # Filter strictly to core nutrients
        df = df[df[nutrient_col].isin(CORE_NUTRIENT_IDS.keys())]

        if active_food_codes is not None:
            active_str_codes = {str(code) for code in active_food_codes}
            df = df[df[food_col].isin(active_str_codes)]

        # Group by food code and assemble profiles
        food_groups: Dict[int, Dict[str, float]] = {}
        for _, row in df.iterrows():
            fc = int(row[food_col])
            nid = row[nutrient_col]
            field = CORE_NUTRIENT_IDS[nid]
            val = float(row[val_col])

            if fc not in food_groups:
                food_groups[fc] = {}
            food_groups[fc][field] = val

        for fc, nuts in food_groups.items():
            self._profiles_per_100g[fc] = NutrientProfile(
                energy_kcal=nuts.get("energy_kcal", 0.0),
                protein_g=nuts.get("protein_g", 0.0),
                fat_g=nuts.get("fat_g", 0.0),
                carbs_g=nuts.get("carbs_g", 0.0),
                fiber_g=nuts.get("fiber_g", 0.0),
                sugar_g=nuts.get("sugar_g", 0.0),
                sodium_mg=nuts.get("sodium_mg", 0.0),
            )

    def get_profile_per_100g(self, food_code: int) -> Optional[NutrientProfile]:
        """Retrieve the per-100g nutrient profile for a CNF food code."""
        return self._profiles_per_100g.get(food_code)

    def calculate_nutrients(
        self,
        food_code: Optional[int],
        grams: Optional[float],
        is_water: bool = False,
    ) -> NutrientProfile:
        """Calculate nutrient amounts for a given food code and mass in grams.

        Returns all zeros if is_water is True, or if food_code/grams is None.
        """
        if is_water or grams is None or grams <= 0 or food_code is None:
            return NutrientProfile()

        profile_100g = self.get_profile_per_100g(int(food_code))
        if profile_100g is None:
            return NutrientProfile()

        return profile_100g.scale(grams)
