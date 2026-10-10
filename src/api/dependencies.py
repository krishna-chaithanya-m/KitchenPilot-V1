"""Dependency Injection and In-Memory Data Store for KitchenPilot-V1 API.

Loads the recommendation engine and recipe catalog once at startup to ensure
high performance, zero per-request model reload, and strict state isolation.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import HTTPException, Request, status

from src.api.config import RECIPE_NUTRITION_PATH, RECIPES_PATH
from src.api.schemas import (
    RecipeDetailResponse,
    RecipeNutritionDetail,
    RecipeSummary,
)
from src.recommendation.recommender import KitchenPilotRecommender

logger = logging.getLogger("kitchenpilot.api")


def _safe_str(val: Any) -> Optional[str]:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    return s if s else None


def _safe_float(val: Any) -> Optional[float]:
    if val is None or pd.isna(val):
        return None
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else round(f, 3)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    if val is None or pd.isna(val):
        return None
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else int(round(f))
    except (ValueError, TypeError):
        return None


def _safe_bool(val: Any) -> Optional[bool]:
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    s = str(val).strip().lower()
    return s in ("true", "1", "yes", "t")


def _calc_confidence(quality: Optional[str]) -> float:
    if not quality:
        return 0.0
    q = quality.upper().strip()
    if q == "HIGH":
        return 1.0
    if q == "MEDIUM":
        return 0.8
    if q in ("LOW", "PARTIAL"):
        return 0.5
    return 0.0


from src.data.repository import BaseRecipeStore, PostgresRecipeStore
from src.data.cuisine_policy import is_indian_cuisine, normalize_cuisine


class RecipeStore(BaseRecipeStore):
    """In-memory indexed store for recipes and frozen nutrition records (CSV Backend)."""

    def __init__(self) -> None:
        self.recipes_df: pd.DataFrame = pd.DataFrame()
        self.nutrition_df: pd.DataFrame = pd.DataFrame()
        self._recipes_by_id: Dict[str, Dict[str, Any]] = {}
        self._nutrition_by_id: Dict[str, RecipeNutritionDetail] = {}
        self._recipe_details_cache: Dict[str, RecipeDetailResponse] = {}
        self.load_data()

    def load_data(self) -> None:
        """Load and index recipe and nutrition datasets."""
        if not RECIPES_PATH.is_file():
            logger.error("Recipes dataset missing at %s", RECIPES_PATH)
            return
        if not RECIPE_NUTRITION_PATH.is_file():
            logger.error("Nutrition dataset missing at %s", RECIPE_NUTRITION_PATH)
            return

        logger.info("Loading recipe catalog and nutrition data into RecipeStore...")
        all_recipes_df = pd.read_csv(RECIPES_PATH, low_memory=False)
        original_count = len(all_recipes_df)

        self.recipes_df = all_recipes_df[
            all_recipes_df["cuisine"].apply(is_indian_cuisine)
        ].copy()
        eligible_ids = set(self.recipes_df["recipe_id"].astype(str).str.strip())

        all_nutrition_df = pd.read_csv(RECIPE_NUTRITION_PATH, low_memory=False)
        self.nutrition_df = all_nutrition_df[
            all_nutrition_df["recipe_id"].astype(str).str.strip().isin(eligible_ids)
        ].copy()

        logger.info(
            "Indian-only catalog filter: %d eligible recipes; %d excluded.",
            len(self.recipes_df),
            original_count - len(self.recipes_df),
        )

        # Index nutrition by recipe_id
        for _, row in self.nutrition_df.iterrows():
            rid = str(row["recipe_id"]).strip()
            q = _safe_str(row.get("nutrition_quality"))
            nut_detail = RecipeNutritionDetail(
                recipe_id=rid,
                recipe_name=str(row.get("recipe_name", "")),
                servings=_safe_float(row.get("servings")),
                calories=_safe_float(row.get("per_serving_calories_kcal")),
                protein=_safe_float(row.get("per_serving_protein_g")),
                fat=_safe_float(row.get("per_serving_fat_g")),
                carbs=_safe_float(row.get("per_serving_carbs_g")),
                fiber=_safe_float(row.get("per_serving_fiber_g")),
                sugar=_safe_float(row.get("per_serving_sugar_g")),
                sodium=_safe_float(row.get("per_serving_sodium_mg")),
                nutrition_quality=q,
                nutrition_confidence=_calc_confidence(q),
                total_calories_kcal=_safe_float(row.get("total_calories_kcal")),
                total_protein_g=_safe_float(row.get("total_protein_g")),
                total_fat_g=_safe_float(row.get("total_fat_g")),
                total_carbs_g=_safe_float(row.get("total_carbs_g")),
                total_fiber_g=_safe_float(row.get("total_fiber_g")),
                total_sugar_g=_safe_float(row.get("total_sugar_g")),
                total_sodium_mg=_safe_float(row.get("total_sodium_mg")),
            )
            self._nutrition_by_id[rid] = nut_detail

        # Index recipes by recipe_id
        for _, row in self.recipes_df.iterrows():
            rid = str(row["recipe_id"]).strip()
            raw_ing = _safe_str(row.get("ingredients"))
            if raw_ing:
                ing_list = [i.strip() for i in raw_ing.split(",") if i.strip()]
            else:
                ing_list = []

            recipe_dict = {
                "recipe_id": rid,
                "recipe_name": str(row.get("recipe_name", "")),
                "name_local": _safe_str(row.get("name_local")),
                "cuisine": _safe_str(row.get("cuisine")),
                "region": _safe_str(row.get("region")),
                "meal_type": _safe_str(row.get("meal_type")),
                "category": _safe_str(row.get("category")),
                "ingredients": ing_list,
                "instructions": _safe_str(row.get("instructions")),
                "prep_time_min": _safe_int(row.get("prep_time_min")),
                "cook_time_min": _safe_int(row.get("cook_time_min")),
                "total_time_min": _safe_int(row.get("total_time_min")),
                "servings": _safe_float(row.get("servings")),
                "diet_type": _safe_str(row.get("diet_type")),
                "vegetarian": _safe_bool(row.get("vegetarian")),
                "vegan": _safe_bool(row.get("vegan")),
                "jain": _safe_bool(row.get("jain")),
                "satvik": _safe_bool(row.get("satvik")),
                "contains": _safe_str(row.get("contains")),
            }
            self._recipes_by_id[rid] = recipe_dict

            # Pre-build detail response with embedded nutrition
            self._recipe_details_cache[rid] = RecipeDetailResponse(
                **recipe_dict,
                nutrition=self._nutrition_by_id.get(rid),
            )

        logger.info(
            "RecipeStore initialized successfully: %d recipes, %d nutrition entries.",
            len(self._recipes_by_id),
            len(self._nutrition_by_id),
        )

    def exists(self, recipe_id: str) -> bool:
        """Check if recipe_id exists in the catalog."""
        return recipe_id in self._recipes_by_id

    def get_recipe(self, recipe_id: str) -> Optional[RecipeDetailResponse]:
        """Fetch pre-computed recipe detail with embedded nutrition."""
        return self._recipe_details_cache.get(recipe_id)

    def get_nutrition(self, recipe_id: str) -> Optional[RecipeNutritionDetail]:
        """Fetch standalone nutrition detail."""
        return self._nutrition_by_id.get(recipe_id)

    def get_recipe_ingredients(self, recipe_id: str) -> List[Dict[str, Any]]:
        """Fetch parsed recipe ingredient lines."""
        rec = self._recipes_by_id.get(recipe_id)
        if rec and rec.get("ingredients"):
            return [{"original_ingredient": ing} for ing in rec["ingredients"]]
        return []

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
        filtered = self.recipes_df

        if cuisine is not None:
            if is_indian_cuisine(cuisine):
                norm_cuisine = normalize_cuisine(cuisine)
                filtered = filtered[filtered["cuisine"].apply(normalize_cuisine) == norm_cuisine]
            else:
                filtered = filtered.iloc[0:0]
        if region:
            filtered = filtered[filtered["region"].astype(str).str.lower() == region.lower().strip()]
        if meal_type:
            filtered = filtered[filtered["meal_type"].astype(str).str.lower() == meal_type.lower().strip()]
        if category:
            filtered = filtered[filtered["category"].astype(str).str.lower() == category.lower().strip()]
        if vegetarian is not None:
            filtered = filtered[filtered["vegetarian"] == vegetarian]
        if vegan is not None:
            filtered = filtered[filtered["vegan"] == vegan]
        if jain is not None:
            filtered = filtered[filtered["jain"] == jain]
        if satvik is not None:
            filtered = filtered[filtered["satvik"] == satvik]

        total = len(filtered)
        total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        slice_df = filtered.iloc[start_idx:end_idx]

        summaries: List[RecipeSummary] = []
        for _, row in slice_df.iterrows():
            summaries.append(
                RecipeSummary(
                    recipe_id=str(row["recipe_id"]),
                    recipe_name=str(row.get("recipe_name", "")),
                    cuisine=_safe_str(row.get("cuisine")),
                    region=_safe_str(row.get("region")),
                    meal_type=_safe_str(row.get("meal_type")),
                    category=_safe_str(row.get("category")),
                    diet_type=_safe_str(row.get("diet_type")),
                    prep_time_min=_safe_int(row.get("prep_time_min")),
                    cook_time_min=_safe_int(row.get("cook_time_min")),
                    total_time_min=_safe_int(row.get("total_time_min")),
                    servings=_safe_float(row.get("servings")),
                    vegetarian=_safe_bool(row.get("vegetarian")),
                    vegan=_safe_bool(row.get("vegan")),
                    jain=_safe_bool(row.get("jain")),
                    satvik=_safe_bool(row.get("satvik")),
                )
            )

        return summaries, total, total_pages


def create_recipe_store(backend: Optional[str] = None) -> BaseRecipeStore:
    """Factory to create appropriate RecipeStore backend based on configuration."""
    import os
    selected_backend = (backend or os.getenv("DATA_BACKEND", "csv")).lower().strip()
    if selected_backend == "postgres":
        logger.info("Initializing PostgreSQL RecipeStore backend...")
        return PostgresRecipeStore()
    logger.info("Initializing CSV RecipeStore backend (default)...")
    return RecipeStore()


# ============================================================================
# Dependency Injection Callables
# ============================================================================

def get_recommender(request: Request) -> KitchenPilotRecommender:
    """FastAPI dependency to retrieve the pre-loaded KitchenPilotRecommender instance."""
    recommender = getattr(request.app.state, "recommender", None)
    if recommender is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recommendation engine is not initialized or model artifacts are missing.",
        )
    return recommender


def get_recipe_store(request: Request) -> BaseRecipeStore:
    """FastAPI dependency to retrieve the pre-loaded RecipeStore instance."""
    store = getattr(request.app.state, "recipe_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recipe catalog store is not initialized.",
        )
    return store


# ============================================================================
# Stage G Authentication & Database Dependencies
# ============================================================================

from typing import Generator
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from src.db.session import get_db_session
from src.personalization.models import UserModel
from src.personalization.security import decode_access_token
from src.personalization.service import PersonalizationService

security_bearer = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a transactional DB session."""
    with get_db_session() as session:
        yield session


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> UserModel:
    """FastAPI dependency requiring an authenticated active user via valid JWT."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or malformed authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = PersonalizationService.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or is inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> Optional[UserModel]:
    """FastAPI dependency returning authenticated user if token present and valid, or None for anonymous."""
    if not credentials or not credentials.credentials:
        return None
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        return None
    try:
        user_id = int(payload["sub"])
        user = PersonalizationService.get_user_by_id(db, user_id)
        if user and user.is_active:
            return user
    except Exception:
        return None
    return None
