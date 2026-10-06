"""Personalization feature extraction and user context definitions for KitchenPilot-V1."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("kitchenpilot.personalization")

PERSONALIZATION_FEATURE_SCHEMA_VERSION = "1.0.0"


@dataclass
class UserPersonalizationContext:
    """Aggregated user context used to personalize recommendations."""
    user_id: int
    vegetarian: bool = False
    vegan: bool = False
    jain: bool = False
    satvik: bool = False
    preferred_cuisines: Set[str] = field(default_factory=set)
    preferred_regions: Set[str] = field(default_factory=set)
    preferred_meal_types: Set[str] = field(default_factory=set)
    preferred_categories: Set[str] = field(default_factory=set)
    preferred_ingredients: Set[str] = field(default_factory=set)
    disliked_ingredients: Set[str] = field(default_factory=set)
    pantry_ingredient_ids: Set[str] = field(default_factory=set)
    pantry_ingredient_names: Set[str] = field(default_factory=set)
    liked_recipe_ids: Set[str] = field(default_factory=set)
    saved_recipe_ids: Set[str] = field(default_factory=set)
    cooked_recipe_ids: Set[str] = field(default_factory=set)
    disliked_recipe_ids: Set[str] = field(default_factory=set)
    hidden_recipe_ids: Set[str] = field(default_factory=set)
    recent_recommended_recipe_ids: Set[str] = field(default_factory=set)
    calorie_target: Optional[float] = None
    min_calories: Optional[float] = None
    max_calories: Optional[float] = None
    protein_target: Optional[float] = None
    min_protein: Optional[float] = None
    max_protein: Optional[float] = None


@dataclass
class PersonalizationSignals:
    """Extracted personalization signals for a single candidate recipe."""
    cuisine_affinity: float = 0.0
    region_affinity: float = 0.0
    meal_type_affinity: float = 0.0
    category_affinity: float = 0.0
    pantry_overlap_count: int = 0
    pantry_overlap_ratio: float = 0.0
    preferred_ingredient_match_count: int = 0
    disliked_ingredient_penalty: float = 0.0
    past_liked: bool = False
    past_saved: bool = False
    past_cooked: bool = False
    past_disliked: bool = False
    past_hidden: bool = False
    recently_recommended: bool = False
    nutrition_target_alignment: float = 0.0
    raw_personalization_score: float = 0.0
    personalization_adjustment: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert signals to dictionary for audit logging and metadata."""
        return {
            "cuisine_affinity": round(self.cuisine_affinity, 4),
            "region_affinity": round(self.region_affinity, 4),
            "meal_type_affinity": round(self.meal_type_affinity, 4),
            "category_affinity": round(self.category_affinity, 4),
            "pantry_overlap_count": self.pantry_overlap_count,
            "pantry_overlap_ratio": round(self.pantry_overlap_ratio, 4),
            "preferred_ingredient_match_count": self.preferred_ingredient_match_count,
            "disliked_ingredient_penalty": round(self.disliked_ingredient_penalty, 4),
            "past_liked": self.past_liked,
            "past_saved": self.past_saved,
            "past_cooked": self.past_cooked,
            "past_disliked": self.past_disliked,
            "past_hidden": self.past_hidden,
            "recently_recommended": self.recently_recommended,
            "nutrition_target_alignment": round(self.nutrition_target_alignment, 4),
            "raw_personalization_score": round(self.raw_personalization_score, 4),
            "personalization_adjustment": round(self.personalization_adjustment, 4),
            "schema_version": PERSONALIZATION_FEATURE_SCHEMA_VERSION,
        }


def extract_personalization_signals(
    recipe_meta: Dict[str, Any],
    context: Optional[UserPersonalizationContext],
) -> PersonalizationSignals:
    """Extract deterministic personalization signals for a candidate recipe given user context.
    
    If context is None, returns zeroed default signals (anonymous baseline parity).
    """
    if context is None:
        return PersonalizationSignals()

    signals = PersonalizationSignals()
    recipe_id = str(recipe_meta.get("recipe_id", "")).strip()
    cuisine = str(recipe_meta.get("cuisine", "")).strip().lower()
    region = str(recipe_meta.get("region", "")).strip().lower()
    meal_type = str(recipe_meta.get("meal_type", "")).strip().lower()
    category = str(recipe_meta.get("category", "")).strip().lower()

    # 1. Metadata affinities
    if cuisine and cuisine in {c.lower() for c in context.preferred_cuisines}:
        signals.cuisine_affinity = 1.0
        signals.reasons.append(f"Matches preferred cuisine ({recipe_meta.get('cuisine')})")

    if region and region in {r.lower() for r in context.preferred_regions}:
        signals.region_affinity = 1.0

    if meal_type and meal_type in {m.lower() for m in context.preferred_meal_types}:
        signals.meal_type_affinity = 1.0

    if category and category in {c.lower() for c in context.preferred_categories}:
        signals.category_affinity = 1.0

    # 2. Ingredient & Pantry overlap
    recipe_ingredients = recipe_meta.get("ingredients_list", []) or []
    if isinstance(recipe_ingredients, str):
        recipe_ingredients = [i.strip() for i in recipe_ingredients.split(",") if i.strip()]

    ing_lower_set = {str(i).strip().lower() for i in recipe_ingredients if i}
    recipe_ing_ids = {str(cid).strip() for cid in recipe_meta.get("ingredient_ids", []) if cid}

    # Pantry match by ID or by normalized name
    pantry_id_matches = recipe_ing_ids.intersection(context.pantry_ingredient_ids)
    pantry_name_matches = ing_lower_set.intersection({p.lower() for p in context.pantry_ingredient_names})
    overlap_count = max(len(pantry_id_matches), len(pantry_name_matches))
    signals.pantry_overlap_count = overlap_count

    total_ings = max(len(recipe_ingredients), 1)
    signals.pantry_overlap_ratio = min(1.0, overlap_count / total_ings)
    if overlap_count > 0:
        signals.reasons.append(f"Uses {overlap_count} ingredient(s) from your pantry")

    # Preferred ingredients
    pref_ing_matches = ing_lower_set.intersection({p.lower() for p in context.preferred_ingredients})
    signals.preferred_ingredient_match_count = len(pref_ing_matches)
    if signals.preferred_ingredient_match_count > 0:
        signals.reasons.append(f"Contains {signals.preferred_ingredient_match_count} of your preferred ingredient(s)")

    # Disliked ingredients (soft penalty; hard exclusions handled prior by Stage E)
    disliked_matches = ing_lower_set.intersection({d.lower() for d in context.disliked_ingredients})
    if disliked_matches:
        signals.disliked_ingredient_penalty = 1.0

    # 3. Explicit feedback history
    if recipe_id in context.liked_recipe_ids:
        signals.past_liked = True
        signals.reasons.append("Previously liked by you")

    if recipe_id in context.saved_recipe_ids:
        signals.past_saved = True
        signals.reasons.append("Saved in your favorites")

    if recipe_id in context.cooked_recipe_ids:
        signals.past_cooked = True
        signals.reasons.append("Previously cooked by you")

    if recipe_id in context.disliked_recipe_ids:
        signals.past_disliked = True

    if recipe_id in context.hidden_recipe_ids:
        signals.past_hidden = True

    # 4. Recommendation repetition / novelty
    if recipe_id in context.recent_recommended_recipe_ids:
        signals.recently_recommended = True

    # 5. Nutrition target alignment
    calories = float(recipe_meta.get("per_serving_calories", 0.0) or 0.0)
    protein = float(recipe_meta.get("per_serving_protein", 0.0) or 0.0)

    nut_alignment = 0.0
    nut_signals_count = 0

    if context.calorie_target and context.calorie_target > 0:
        nut_signals_count += 1
        cal_dist = abs(calories - context.calorie_target) / context.calorie_target
        nut_alignment += max(0.0, 1.0 - cal_dist)
    elif context.max_calories and context.max_calories > 0:
        nut_signals_count += 1
        if calories <= context.max_calories:
            nut_alignment += 1.0
        else:
            nut_alignment += max(0.0, 1.0 - (calories - context.max_calories) / context.max_calories)

    if context.protein_target and context.protein_target > 0:
        nut_signals_count += 1
        prot_dist = abs(protein - context.protein_target) / max(context.protein_target, 1.0)
        nut_alignment += max(0.0, 1.0 - prot_dist)

    if nut_signals_count > 0:
        signals.nutrition_target_alignment = nut_alignment / nut_signals_count
        if signals.nutrition_target_alignment >= 0.75:
            signals.reasons.append("Aligns with your nutrition targets")

    return signals
