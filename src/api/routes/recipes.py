"""Recipe Catalog and Nutrition Route Endpoints for KitchenPilot-V1 API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.dependencies import RecipeStore, get_recipe_store, get_recommender
from src.api.schemas import (
    RecipeDetailResponse,
    RecipeListResponse,
    RecipeNutritionDetail,
    RecommendationItem,
    RecommendationResponse,
)
from src.recommendation.recommender import KitchenPilotRecommender

router = APIRouter(prefix="/api/v1/recipes", tags=["Recipes & Nutrition"])


def _format_recommendations_from_df(df: pd.DataFrame) -> List[RecommendationItem]:
    """Convert recommendation DataFrame into validated Pydantic items."""
    items: List[RecommendationItem] = []
    if df.empty:
        return items

    for _, row in df.iterrows():
        raw_matched = str(row.get("matched_ingredients", ""))
        matched_list = [
            i.strip()
            for i in raw_matched.split(",")
            if i.strip() and i.strip().lower() != "nan"
        ]
        raw_missing = str(row.get("missing_ingredients", ""))
        missing_list = [
            i.strip()
            for i in raw_missing.split(",")
            if i.strip() and i.strip().lower() != "nan"
        ]

        items.append(
            RecommendationItem(
                rank=int(row["rank"]),
                recipe_id=str(row["recipe_id"]),
                recipe_name=str(row["recipe_name"]),
                hybrid_score=round(float(row["hybrid_score"]), 4),
                similarity_score=round(float(row["similarity_score"]), 4),
                ingredient_match_score=round(float(row["ingredient_match_score"]), 4),
                nutrition_score=round(float(row["nutrition_score"]), 4),
                preference_score=round(float(row["preference_score"]), 4),
                nutrition_confidence=row["nutrition_confidence"],
                matched_ingredients=matched_list,
                missing_ingredients=missing_list,
                explanation=str(row["explanation"]),
            )
        )
    return items


@router.get(
    "",
    response_model=RecipeListResponse,
    summary="List Recipes (Paginated)",
    description="Query catalog recipes with pagination and filtering across cuisine, region, meal_type, category, and dietary flags.",
)
def list_recipes(
    page: int = Query(1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    cuisine: Optional[str] = Query(None, description="Filter by cuisine (case-insensitive)"),
    region: Optional[str] = Query(None, description="Filter by region (case-insensitive)"),
    meal_type: Optional[str] = Query(None, description="Filter by meal type (case-insensitive)"),
    category: Optional[str] = Query(None, description="Filter by category (case-insensitive)"),
    vegetarian: Optional[bool] = Query(None, description="Filter vegetarian recipes"),
    vegan: Optional[bool] = Query(None, description="Filter vegan recipes"),
    jain: Optional[bool] = Query(None, description="Filter Jain recipes"),
    satvik: Optional[bool] = Query(None, description="Filter Satvik recipes"),
    store: RecipeStore = Depends(get_recipe_store),
) -> RecipeListResponse:
    """Return paginated recipe summaries."""
    summaries, total, total_pages = store.list_recipes(
        page=page,
        page_size=page_size,
        cuisine=cuisine,
        region=region,
        meal_type=meal_type,
        category=category,
        vegetarian=vegetarian,
        vegan=vegan,
        jain=jain,
        satvik=satvik,
    )
    return RecipeListResponse(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        recipes=summaries,
    )


@router.get(
    "/{recipe_id}",
    response_model=RecipeDetailResponse,
    summary="Get Recipe Details",
    description="Retrieve full metadata, ingredient list, instructions, and embedded nutrition for a single recipe.",
)
def get_recipe_detail(
    recipe_id: str,
    store: RecipeStore = Depends(get_recipe_store),
) -> RecipeDetailResponse:
    """Fetch recipe details by recipe ID."""
    recipe = store.get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recipe not found: {recipe_id}",
        )
    return recipe


@router.get(
    "/{recipe_id}/nutrition",
    response_model=RecipeNutritionDetail,
    summary="Get Recipe Nutrition",
    description="Read deterministic nutrition profile from frozen nutrition data without recalculation.",
)
def get_recipe_nutrition(
    recipe_id: str,
    store: RecipeStore = Depends(get_recipe_store),
) -> RecipeNutritionDetail:
    """Retrieve frozen nutrition profile for a recipe."""
    if not store.exists(recipe_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recipe not found: {recipe_id}",
        )
    nut = store.get_nutrition(recipe_id)
    if nut is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nutrition data not found for recipe: {recipe_id}",
        )
    return nut


@router.get(
    "/{recipe_id}/similar",
    response_model=RecommendationResponse,
    summary="Find Similar Recipes",
    description="Find the most similar recipes to a query recipe using the frozen TF-IDF and hybrid recommendation engine.",
)
def get_similar_recipes(
    recipe_id: str,
    top_k: int = Query(10, ge=1, le=50, description="Number of recommendations to return (1-50)"),
    store: RecipeStore = Depends(get_recipe_store),
    recommender: KitchenPilotRecommender = Depends(get_recommender),
) -> RecommendationResponse:
    """Find similar recipes by recipe ID."""
    if not store.exists(recipe_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recipe not found: {recipe_id}",
        )

    results_df = recommender.recommend(
        query_recipe_id=recipe_id,
        top_k=top_k,
        save_results=False,
    )
    items = _format_recommendations_from_df(results_df)

    return RecommendationResponse(
        query={
            "query_recipe_id": recipe_id,
            "top_k": top_k,
            "mode": "recipe_similarity",
        },
        count=len(items),
        recommendations=items,
    )
