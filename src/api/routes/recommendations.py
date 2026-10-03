"""Recommendation Route Endpoints for KitchenPilot-V1 API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import RecipeStore, get_recipe_store, get_recommender
from src.api.routes.recipes import _format_recommendations_from_df
from src.api.schemas import (
    IngredientRecommendRequest,
    NutritionGoalsRequest,
    RecommendationResponse,
    RecommendRequest,
    UserPreferencesRequest,
)
from src.recommendation.nutrition_scorer import NutritionGoals
from src.recommendation.preference_filter import UserPreferences
from src.recommendation.recommender import KitchenPilotRecommender

router = APIRouter(prefix="/api/v1/recommend", tags=["Recommendations"])


def _to_engine_preferences(req_prefs: Optional[UserPreferencesRequest]) -> Optional[UserPreferences]:
    """Convert API preferences request schema to recommendation engine dataclass."""
    if req_prefs is None:
        return None
    return UserPreferences(
        vegetarian=req_prefs.vegetarian,
        vegan=req_prefs.vegan,
        jain=req_prefs.jain,
        satvik=req_prefs.satvik,
        diet_type=req_prefs.diet_type,
        cuisine=req_prefs.cuisine,
        region=req_prefs.region,
        meal_type=req_prefs.meal_type,
        category=req_prefs.category,
        excluded_ingredients=req_prefs.excluded_ingredients or [],
        required_ingredients=req_prefs.required_ingredients or [],
    )


def _to_engine_goals(req_goals: Optional[NutritionGoalsRequest]) -> Optional[NutritionGoals]:
    """Convert API nutrition goals request schema to recommendation engine dataclass."""
    if req_goals is None:
        return None
    return NutritionGoals(
        calorie_target=req_goals.calorie_target,
        max_calories=req_goals.max_calories,
        min_protein=req_goals.min_protein,
        max_fat=req_goals.max_fat,
        max_carbs=req_goals.max_carbs,
        min_fiber=req_goals.min_fiber,
    )


@router.post(
    "",
    response_model=RecommendationResponse,
    summary="Generate Hybrid Recommendations",
    description="Main recommendation endpoint supporting recipe-similarity mode, ingredient-matching mode, dietary hard filtering, nutrition targeting, and hybrid ranking.",
)
def generate_recommendations(
    request: RecommendRequest,
    store: RecipeStore = Depends(get_recipe_store),
    recommender: KitchenPilotRecommender = Depends(get_recommender),
) -> RecommendationResponse:
    """Execute hybrid recommendation pipeline."""
    if request.query_recipe_id and not store.exists(request.query_recipe_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Query recipe not found: {request.query_recipe_id}",
        )

    prefs = _to_engine_preferences(request.user_preferences)
    goals = _to_engine_goals(request.nutrition_goals)

    results_df = recommender.recommend(
        query_recipe_id=request.query_recipe_id,
        available_ingredients=request.available_ingredients,
        user_preferences=prefs,
        nutrition_goals=goals,
        top_k=request.top_k,
        save_results=False,
    )
    items = _format_recommendations_from_df(results_df)

    query_meta: Dict[str, Any] = {
        "query_recipe_id": request.query_recipe_id,
        "available_ingredients": request.available_ingredients or [],
        "user_preferences": request.user_preferences.model_dump() if request.user_preferences else {},
        "nutrition_goals": request.nutrition_goals.model_dump() if request.nutrition_goals else {},
        "top_k": request.top_k,
    }

    return RecommendationResponse(
        query=query_meta,
        count=len(items),
        recommendations=items,
    )


@router.post(
    "/by-ingredients",
    response_model=RecommendationResponse,
    summary="Ingredient-Based Recommendations",
    description="Pantry/ingredient focused recommendation endpoint to find recipes matching available ingredients with preference and nutrition filtering.",
)
def recommend_by_ingredients(
    request: IngredientRecommendRequest,
    recommender: KitchenPilotRecommender = Depends(get_recommender),
) -> RecommendationResponse:
    """Execute ingredient-focused recommendation."""
    prefs = _to_engine_preferences(request.user_preferences)
    goals = _to_engine_goals(request.nutrition_goals)

    results_df = recommender.recommend(
        available_ingredients=request.ingredients,
        user_preferences=prefs,
        nutrition_goals=goals,
        top_k=request.top_k,
        save_results=False,
    )
    items = _format_recommendations_from_df(results_df)

    query_meta: Dict[str, Any] = {
        "ingredients": request.ingredients,
        "user_preferences": request.user_preferences.model_dump() if request.user_preferences else {},
        "nutrition_goals": request.nutrition_goals.model_dump() if request.nutrition_goals else {},
        "top_k": request.top_k,
        "mode": "ingredient_based",
    }

    return RecommendationResponse(
        query=query_meta,
        count=len(items),
        recommendations=items,
    )
