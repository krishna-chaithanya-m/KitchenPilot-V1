"""Preference Filter for KitchenPilot-V1 Recommendation Engine.

Applies strict hard filters (dietary restrictions, excluded/required ingredients)
and computes soft preference compatibility scores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import pandas as pd

from src.constraints.dietary import DietaryRuleEngine
from src.constraints.models import DietaryConstraints
from src.recommendation.config import RecommendationConfig
from src.recommendation.ingredient_matcher import IngredientMatcher


@dataclass
class UserPreferences:
    """User preferences, dietary constraints, and exclusions."""
    vegetarian: Optional[bool] = None
    vegan: Optional[bool] = None
    jain: Optional[bool] = None
    satvik: Optional[bool] = None

    diet_type: Optional[Union[str, List[str]]] = None
    cuisine: Optional[Union[str, List[str]]] = None
    region: Optional[Union[str, List[str]]] = None
    meal_type: Optional[Union[str, List[str]]] = None
    category: Optional[Union[str, List[str]]] = None

    excluded_ingredients: Optional[List[str]] = field(default_factory=list)
    required_ingredients: Optional[List[str]] = field(default_factory=list)
    disliked_ingredients: Optional[List[str]] = field(default_factory=list)

    max_prep_time_min: Optional[float] = None
    max_total_time_min: Optional[float] = None


class PreferenceFilter:
    """Applies hard dietary/exclusion filters and calculates preference compatibility scores."""

    def __init__(self, config: Optional[RecommendationConfig] = None) -> None:
        self.config = config or RecommendationConfig()
        self._recipes_metadata: Dict[str, Dict[str, any]] = {}
        self._load_recipes_metadata()
        self._dietary_engine = DietaryRuleEngine(recipes_path=self.config.recipes_path)

    def _load_recipes_metadata(self) -> None:
        """Load recipe metadata relevant to dietary filtering and preferences."""
        df = pd.read_csv(self.config.recipes_path)
        for _, row in df.iterrows():
            rid = str(row["recipe_id"]).strip()
            self._recipes_metadata[rid] = {
                "recipe_name": str(row["recipe_name"]) if pd.notna(row["recipe_name"]) else "",
                "cuisine": str(row["cuisine"]).lower().strip() if pd.notna(row.get("cuisine")) else "",
                "region": str(row["region"]).lower().strip() if pd.notna(row.get("region")) else "",
                "meal_type": str(row["meal_type"]).lower().strip() if pd.notna(row.get("meal_type")) else "",
                "category": str(row["category"]).lower().strip() if pd.notna(row.get("category")) else "",
                "diet_type": str(row["diet_type"]).lower().strip() if pd.notna(row.get("diet_type")) else "",
                "vegetarian": bool(row["vegetarian"]) if pd.notna(row.get("vegetarian")) else False,
                "vegan": bool(row["vegan"]) if pd.notna(row.get("vegan")) else False,
                "jain": bool(row["jain"]) if pd.notna(row.get("jain")) else False,
                "satvik": bool(row["satvik"]) if pd.notna(row.get("satvik")) else False,
                "prep_time_min": float(row["prep_time_min"]) if pd.notna(row.get("prep_time_min")) else None,
                "total_time_min": float(row["total_time_min"]) if pd.notna(row.get("total_time_min")) else None,
            }

    def _to_clean_list(self, val: Optional[Union[str, List[str]]]) -> List[str]:
        """Convert a string or list of strings into a normalized list."""
        if val is None:
            return []
        if isinstance(val, str):
            return [val.lower().strip()]
        return [str(v).lower().strip() for v in val if v]

    def passes_hard_filters(
        self,
        recipe_id: str,
        preferences: UserPreferences,
        matcher: IngredientMatcher,
    ) -> bool:
        """Evaluate whether a recipe strictly passes all hard exclusion/dietary filters."""
        meta = self._recipes_metadata.get(recipe_id)
        if not meta:
            return False

        # 1-4. Dietary constraints (Vegetarian, Vegan, Jain, Satvik) evaluated via canonical rule engine
        if any([
            preferences.vegetarian is True,
            preferences.vegan is True,
            preferences.jain is True,
            preferences.satvik is True,
        ]):
            diet_c = DietaryConstraints(
                vegetarian=preferences.vegetarian,
                vegan=preferences.vegan,
                jain=preferences.jain,
                satvik=preferences.satvik,
            )
            passed, _, _ = self._dietary_engine.evaluate_dietary_compliance(recipe_id, diet_c)
            if not passed:
                return False

        # 5. Total time limit
        if preferences.max_total_time_min is not None and preferences.max_total_time_min > 0:
            tt = meta["total_time_min"]
            if tt is not None and tt > preferences.max_total_time_min:
                return False

        # 6. Excluded ingredients (HARD FILTER: must NEVER appear in final results)
        if preferences.excluded_ingredients:
            excluded_set = matcher.resolve_ingredient_list(preferences.excluded_ingredients)
            recipe_canons = matcher._recipe_canonical_map.get(recipe_id, set())
            for exc in excluded_set:
                if exc in recipe_canons:
                    return False
                # Also check raw ingredient names in recipe
                all_ings = matcher._recipe_all_ingredients.get(recipe_id, [])
                if any(exc in ing or ing in exc for ing in all_ings):
                    return False

        # 7. Required ingredients (HARD FILTER: all must be present)
        if preferences.required_ingredients:
            req_set = matcher.resolve_ingredient_list(preferences.required_ingredients)
            recipe_canons = matcher._recipe_canonical_map.get(recipe_id, set())
            if not req_set.issubset(recipe_canons):
                return False

        return True

    def compute_preference_score(
        self,
        recipe_id: str,
        preferences: Optional[UserPreferences] = None,
    ) -> Tuple[float, List[str]]:
        """Compute soft preference compatibility score [0.0, 1.0] and matched preferences."""
        meta = self._recipes_metadata.get(recipe_id)
        if not meta:
            return 0.0, []

        if preferences is None:
            return 1.0, []

        matched_prefs: List[str] = []
        checks = 0
        score_accum = 0.0

        # Check dietary alignments
        if preferences.vegetarian is not None:
            checks += 1
            if meta["vegetarian"] == preferences.vegetarian:
                score_accum += 1.0
                if preferences.vegetarian:
                    matched_prefs.append("Vegetarian")

        if preferences.vegan is not None:
            checks += 1
            is_vegan = meta["vegan"] or ("vegan" in meta["diet_type"])
            if is_vegan == preferences.vegan:
                score_accum += 1.0
                if preferences.vegan:
                    matched_prefs.append("Vegan")

        if preferences.cuisine:
            checks += 1
            cuisines = self._to_clean_list(preferences.cuisine)
            if any(c in meta["cuisine"] for c in cuisines):
                score_accum += 1.0
                matched_prefs.append(f"Cuisine: {meta['cuisine'].title()}")

        if preferences.meal_type:
            checks += 1
            meal_types = self._to_clean_list(preferences.meal_type)
            if any(m in meta["meal_type"] for m in meal_types):
                score_accum += 1.0
                matched_prefs.append(f"Meal: {meta['meal_type'].title()}")

        if preferences.category:
            checks += 1
            categories = self._to_clean_list(preferences.category)
            if any(cat in meta["category"] for cat in categories):
                score_accum += 1.0
                matched_prefs.append(f"Category: {meta['category'].title()}")

        if preferences.region:
            checks += 1
            regions = self._to_clean_list(preferences.region)
            if any(r in meta["region"] for r in regions):
                score_accum += 1.0
                matched_prefs.append(f"Region: {meta['region'].title()}")

        if checks == 0:
            return 1.0, matched_prefs

        final_score = round(score_accum / checks, 4)
        return min(1.0, max(0.0, final_score)), matched_prefs
