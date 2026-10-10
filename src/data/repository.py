"""Repository abstraction layer separating application logic from persistence backends."""

from __future__ import annotations

import abc
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import func, select

from src.api.schemas import (
    RecipeDetailResponse,
    RecipeNutritionDetail,
    RecipeSummary,
)
from src.db.models import (
    IngredientModel,
    RecipeIngredientModel,
    RecipeModel,
    RecipeNutritionModel,
)
from src.db.session import get_db_session
from src.data.cuisine_policy import INDIAN_CUISINES, is_indian_cuisine, normalize_cuisine


logger = logging.getLogger("kitchenpilot.repository")


def _calc_confidence(quality: Optional[str]) -> float:
    if not quality:
        return 0.0
    q = quality.upper().strip()
    if q == "HIGH" or q == "COMPLETE":
        return 1.0
    if q == "MEDIUM":
        return 0.8
    if q in ("LOW", "PARTIAL", "APPROXIMATE"):
        return 0.5
    return 0.0


def _safe_float(val: Any) -> Optional[float]:
    if val is None or pd.isna(val):
        return None
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else round(f, 3)
    except (ValueError, TypeError):
        return None


class BaseRecipeStore(abc.ABC):
    """Abstract contract for recipe and nutrition catalog stores."""

    @abc.abstractmethod
    def exists(self, recipe_id: str) -> bool:
        """Check if recipe_id exists in the catalog."""
        pass

    @abc.abstractmethod
    def get_recipe(self, recipe_id: str) -> Optional[RecipeDetailResponse]:
        """Fetch recipe detail with embedded nutrition."""
        pass

    @abc.abstractmethod
    def get_nutrition(self, recipe_id: str) -> Optional[RecipeNutritionDetail]:
        """Fetch standalone nutrition detail for a recipe."""
        pass

    @abc.abstractmethod
    def list_recipes(
        self,
        page: int = 1,
        page_size: int = 20,
        cuisine: Optional[str] = None,
        region: Optional[str] = None,
        meal_type: Optional[str] = None,
        category: Optional[str] = None,
        vegetarian: Optional[bool] = None,
        vegan: Optional[bool] = None,
        jain: Optional[bool] = None,
        satvik: Optional[bool] = None,
    ) -> Tuple[List[RecipeSummary], int, int]:
        """Paginated, filtered list of recipe summaries."""
        pass

    @abc.abstractmethod
    def get_recipe_ingredients(self, recipe_id: str) -> List[Dict[str, Any]]:
        """Fetch parsed recipe ingredient lines for a recipe."""
        pass


class PostgresRecipeStore(BaseRecipeStore):
    """Production PostgreSQL-backed implementation of BaseRecipeStore."""

    def exists(self, recipe_id: str) -> bool:
        """Check whether an approved Indian recipe exists in PostgreSQL."""
        with get_db_session() as session:
            stmt = select(RecipeModel.cuisine).where(RecipeModel.recipe_id == recipe_id)
            cuisine = session.scalar(stmt)
            return is_indian_cuisine(cuisine)

    def get_recipe(self, recipe_id: str) -> Optional[RecipeDetailResponse]:
        """Fetch recipe detail with embedded nutrition from PostgreSQL."""
        with get_db_session() as session:
            stmt = select(RecipeModel).where(RecipeModel.recipe_id == recipe_id)
            recipe = session.scalar(stmt)
            if not recipe or not is_indian_cuisine(recipe.cuisine):
                return None

            nut_detail: Optional[RecipeNutritionDetail] = None
            if recipe.nutrition:
                n = recipe.nutrition
                q = n.nutrition_quality
                nut_detail = RecipeNutritionDetail(
                    recipe_id=n.recipe_id,
                    recipe_name=n.recipe_name,
                    servings=_safe_float(n.servings),
                    calories=_safe_float(n.per_serving_calories_kcal),
                    protein=_safe_float(n.per_serving_protein_g),
                    fat=_safe_float(n.per_serving_fat_g),
                    carbs=_safe_float(n.per_serving_carbs_g),
                    fiber=_safe_float(n.per_serving_fiber_g),
                    sugar=_safe_float(n.per_serving_sugar_g),
                    sodium=_safe_float(n.per_serving_sodium_mg),
                    nutrition_quality=q,
                    nutrition_confidence=_calc_confidence(q),
                    total_calories_kcal=_safe_float(n.total_calories_kcal),
                    total_protein_g=_safe_float(n.total_protein_g),
                    total_fat_g=_safe_float(n.total_fat_g),
                    total_carbs_g=_safe_float(n.total_carbs_g),
                    total_fiber_g=_safe_float(n.total_fiber_g),
                    total_sugar_g=_safe_float(n.total_sugar_g),
                    total_sodium_mg=_safe_float(n.total_sodium_mg),
                )

            ing_list: List[str] = []
            if recipe.ingredients:
                ing_list = [i.strip() for i in recipe.ingredients.split(",") if i.strip()]

            return RecipeDetailResponse(
                recipe_id=recipe.recipe_id,
                recipe_name=recipe.recipe_name,
                name_local=recipe.name_local,
                cuisine=recipe.cuisine,
                region=recipe.region,
                meal_type=recipe.meal_type,
                category=recipe.category,
                ingredients=ing_list,
                instructions=recipe.instructions,
                prep_time_min=recipe.prep_time_min,
                cook_time_min=recipe.cook_time_min,
                total_time_min=recipe.total_time_min,
                servings=float(recipe.servings),
                diet_type=recipe.diet_type,
                vegetarian=recipe.vegetarian,
                vegan=recipe.vegan,
                jain=recipe.jain,
                satvik=recipe.satvik,
                contains=recipe.contains,
                nutrition=nut_detail,
            )

    def get_nutrition(self, recipe_id: str) -> Optional[RecipeNutritionDetail]:
        """Fetch standalone nutrition detail from PostgreSQL."""
        with get_db_session() as session:
            recipe_stmt = select(RecipeModel.cuisine).where(
                RecipeModel.recipe_id == recipe_id
            )
            cuisine = session.scalar(recipe_stmt)
            if not is_indian_cuisine(cuisine):
                return None

            stmt = select(RecipeNutritionModel).where(
                RecipeNutritionModel.recipe_id == recipe_id
            )
            n = session.scalar(stmt)
            if not n:
                return None

            q = n.nutrition_quality
            return RecipeNutritionDetail(
                recipe_id=n.recipe_id,
                recipe_name=n.recipe_name,
                servings=_safe_float(n.servings),
                calories=_safe_float(n.per_serving_calories_kcal),
                protein=_safe_float(n.per_serving_protein_g),
                fat=_safe_float(n.per_serving_fat_g),
                carbs=_safe_float(n.per_serving_carbs_g),
                fiber=_safe_float(n.per_serving_fiber_g),
                sugar=_safe_float(n.per_serving_sugar_g),
                sodium=_safe_float(n.per_serving_sodium_mg),
                nutrition_quality=q,
                nutrition_confidence=_calc_confidence(q),
                total_calories_kcal=_safe_float(n.total_calories_kcal),
                total_protein_g=_safe_float(n.total_protein_g),
                total_fat_g=_safe_float(n.total_fat_g),
                total_carbs_g=_safe_float(n.total_carbs_g),
                total_fiber_g=_safe_float(n.total_fiber_g),
                total_sugar_g=_safe_float(n.total_sugar_g),
                total_sodium_mg=_safe_float(n.total_sodium_mg),
            )

    def list_recipes(
        self,
        page: int = 1,
        page_size: int = 20,
        cuisine: Optional[str] = None,
        region: Optional[str] = None,
        meal_type: Optional[str] = None,
        category: Optional[str] = None,
        vegetarian: Optional[bool] = None,
        vegan: Optional[bool] = None,
        jain: Optional[bool] = None,
        satvik: Optional[bool] = None,
    ) -> Tuple[List[RecipeSummary], int, int]:
        """Paginated list restricted to approved Indian-cuisine recipes."""
        with get_db_session() as session:
            # Push approved Indian cuisine allow-list directly into SQL query
            # Normalizes mixed case, leading/trailing whitespace, and repeated internal whitespace
            normalized_cuisine_expr = func.trim(
                func.regexp_replace(func.lower(RecipeModel.cuisine), r"\s+", " ", "g")
            )
            stmt = select(RecipeModel).where(
                normalized_cuisine_expr.in_(list(INDIAN_CUISINES))
            )
            if cuisine is not None:
                if is_indian_cuisine(cuisine):
                    norm_cuisine = normalize_cuisine(cuisine)
                    stmt = stmt.where(normalized_cuisine_expr == norm_cuisine)
                else:
                    stmt = stmt.where(RecipeModel.recipe_id == "__NO_MATCH__")
            if region:
                stmt = stmt.where(func.lower(RecipeModel.region) == region.lower().strip())
            if meal_type:
                stmt = stmt.where(func.lower(RecipeModel.meal_type) == meal_type.lower().strip())
            if category:
                stmt = stmt.where(func.lower(RecipeModel.category) == category.lower().strip())
            if vegetarian is not None:
                stmt = stmt.where(RecipeModel.vegetarian == vegetarian)
            if vegan is not None:
                stmt = stmt.where(RecipeModel.vegan == vegan)
            if jain is not None:
                stmt = stmt.where(RecipeModel.jain == jain)
            if satvik is not None:
                stmt = stmt.where(RecipeModel.satvik == satvik)

            # Total count computed in SQL without pulling rows into Python
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = session.scalar(count_stmt) or 0
            total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

            # Bounded SQL-level pagination
            offset = max(0, (page - 1) * page_size)
            records_stmt = stmt.order_by(RecipeModel.recipe_id).offset(offset).limit(page_size)
            results = session.scalars(records_stmt).all()

            summaries: List[RecipeSummary] = [
                RecipeSummary(
                    recipe_id=r.recipe_id,
                    recipe_name=r.recipe_name,
                    cuisine=r.cuisine,
                    region=r.region,
                    meal_type=r.meal_type,
                    category=r.category,
                    diet_type=r.diet_type,
                    prep_time_min=r.prep_time_min,
                    cook_time_min=r.cook_time_min,
                    total_time_min=r.total_time_min,
                    servings=float(r.servings),
                    vegetarian=r.vegetarian,
                    vegan=r.vegan,
                    jain=r.jain,
                    satvik=r.satvik,
                )
                for r in results
            ]
            return summaries, total, total_pages
    def get_recipe_ingredients(self, recipe_id: str) -> List[Dict[str, Any]]:
        """Fetch parsed recipe ingredient lines for a recipe from PostgreSQL."""
        with get_db_session() as session:
            recipe_stmt = select(RecipeModel.cuisine).where(
                RecipeModel.recipe_id == recipe_id
            )
            cuisine = session.scalar(recipe_stmt)
            if not is_indian_cuisine(cuisine):
                return []

            stmt = (
                select(RecipeIngredientModel)
                .where(RecipeIngredientModel.recipe_id == recipe_id)
                .order_by(RecipeIngredientModel.id)
            )
            items = session.scalars(stmt).all()
            return [
                {
                    "original_ingredient": item.original_ingredient,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "ingredient": item.ingredient,
                    "preparation": item.preparation,
                    "ingredient_id": item.ingredient_id,
                    "canonical_ingredient": item.canonical_ingredient,
                    "display_name": item.display_name,
                    "mapping_status": item.mapping_status,
                }
                for item in items
            ]
