"""Pydantic Request and Response Schemas for KitchenPilot-V1 API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================================
# Health & Status Schemas
# ============================================================================

class HealthResponse(BaseModel):
    """Health check status response."""
    status: str = "ok"
    service: str = "KitchenPilot-V1"
    version: str = "1.0.0"


class ReadinessResponse(BaseModel):
    """Readiness probe response verifying artifacts and datasets."""
    status: str
    service: str = "KitchenPilot-V1"
    version: str = "1.0.0"
    checks: Dict[str, bool]


# ============================================================================
# Nutrition Schemas
# ============================================================================

class RecipeNutritionDetail(BaseModel):
    """Detailed nutrition profile for a recipe."""
    recipe_id: str
    recipe_name: str
    servings: Optional[float] = None
    calories: Optional[float] = None
    protein: Optional[float] = None
    fat: Optional[float] = None
    carbs: Optional[float] = None
    fiber: Optional[float] = None
    sugar: Optional[float] = None
    sodium: Optional[float] = None
    nutrition_quality: Optional[str] = None
    nutrition_confidence: Optional[float] = None
    total_calories_kcal: Optional[float] = None
    total_protein_g: Optional[float] = None
    total_fat_g: Optional[float] = None
    total_carbs_g: Optional[float] = None
    total_fiber_g: Optional[float] = None
    total_sugar_g: Optional[float] = None
    total_sodium_mg: Optional[float] = None

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# Recipe Catalog Schemas
# ============================================================================

class RecipeSummary(BaseModel):
    """Summary item for recipe catalog listings."""
    recipe_id: str
    recipe_name: str
    cuisine: Optional[str] = None
    region: Optional[str] = None
    meal_type: Optional[str] = None
    category: Optional[str] = None
    diet_type: Optional[str] = None
    prep_time_min: Optional[int] = None
    cook_time_min: Optional[int] = None
    total_time_min: Optional[int] = None
    servings: Optional[float] = None
    vegetarian: Optional[bool] = None
    vegan: Optional[bool] = None
    jain: Optional[bool] = None
    satvik: Optional[bool] = None

    model_config = ConfigDict(extra="ignore")


class RecipeListResponse(BaseModel):
    """Paginated recipe summary response."""
    page: int
    page_size: int
    total: int
    total_pages: int
    recipes: List[RecipeSummary]


class RecipeDetailResponse(BaseModel):
    """Complete recipe detail view."""
    recipe_id: str
    recipe_name: str
    name_local: Optional[str] = None
    cuisine: Optional[str] = None
    region: Optional[str] = None
    meal_type: Optional[str] = None
    category: Optional[str] = None
    ingredients: List[str]
    instructions: Optional[str] = None
    prep_time_min: Optional[int] = None
    cook_time_min: Optional[int] = None
    total_time_min: Optional[int] = None
    servings: Optional[float] = None
    diet_type: Optional[str] = None
    vegetarian: Optional[bool] = None
    vegan: Optional[bool] = None
    jain: Optional[bool] = None
    satvik: Optional[bool] = None
    contains: Optional[str] = None
    nutrition: Optional[RecipeNutritionDetail] = None

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# Recommendation Request Schemas
# ============================================================================

def _clean_str_list(v: Any, field_name: str) -> Optional[List[str]]:
    if v is None:
        return None
    if not isinstance(v, list):
        raise ValueError(f"{field_name} must be a list of strings")
    cleaned = []
    for item in v:
        if not isinstance(item, str):
            raise ValueError(f"Every element in {field_name} must be a string")
        s = item.strip()
        if not s:
            raise ValueError(f"Elements in {field_name} cannot be empty strings")
        cleaned.append(s)
    return cleaned


class UserPreferencesRequest(BaseModel):
    """User dietary preferences and ingredient restrictions."""
    vegetarian: Optional[bool] = None
    vegan: Optional[bool] = None
    jain: Optional[bool] = None
    satvik: Optional[bool] = None
    diet_type: Optional[str] = None
    cuisine: Optional[str] = None
    region: Optional[str] = None
    meal_type: Optional[str] = None
    category: Optional[str] = None
    excluded_ingredients: Optional[List[str]] = None
    required_ingredients: Optional[List[str]] = None

    @field_validator("excluded_ingredients", mode="before")
    @classmethod
    def validate_excluded(cls, v: Any) -> Optional[List[str]]:
        return _clean_str_list(v, "excluded_ingredients")

    @field_validator("required_ingredients", mode="before")
    @classmethod
    def validate_required(cls, v: Any) -> Optional[List[str]]:
        return _clean_str_list(v, "required_ingredients")

    model_config = ConfigDict(extra="forbid")


class NutritionGoalsRequest(BaseModel):
    """Nutritional targets and boundaries (must be non-negative)."""
    calorie_target: Optional[float] = Field(None, ge=0.0)
    max_calories: Optional[float] = Field(None, ge=0.0)
    min_protein: Optional[float] = Field(None, ge=0.0)
    max_fat: Optional[float] = Field(None, ge=0.0)
    max_carbs: Optional[float] = Field(None, ge=0.0)
    min_fiber: Optional[float] = Field(None, ge=0.0)

    model_config = ConfigDict(extra="forbid")


class RecommendRequest(BaseModel):
    """Main recommendation request schema."""
    query_recipe_id: Optional[str] = None
    available_ingredients: Optional[List[str]] = None
    user_preferences: Optional[UserPreferencesRequest] = None
    nutrition_goals: Optional[NutritionGoalsRequest] = None
    top_k: int = Field(default=10, ge=1, le=50)

    @field_validator("available_ingredients", mode="before")
    @classmethod
    def validate_available(cls, v: Any) -> Optional[List[str]]:
        return _clean_str_list(v, "available_ingredients")

    model_config = ConfigDict(extra="forbid")


class IngredientRecommendRequest(BaseModel):
    """Ingredient-focused recommendation request schema."""
    ingredients: List[str] = Field(default_factory=list)
    user_preferences: Optional[UserPreferencesRequest] = None
    nutrition_goals: Optional[NutritionGoalsRequest] = None
    top_k: int = Field(default=10, ge=1, le=50)

    @field_validator("ingredients", mode="before")
    @classmethod
    def validate_ingredients(cls, v: Any) -> List[str]:
        cleaned = _clean_str_list(v, "ingredients")
        return cleaned if cleaned is not None else []

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Recommendation Response Schemas
# ============================================================================

class RecommendationItem(BaseModel):
    """A single ranked recipe recommendation with transparent explainability."""
    rank: int
    recipe_id: str
    recipe_name: str
    hybrid_score: float
    similarity_score: float
    ingredient_match_score: float
    nutrition_score: float
    preference_score: float
    nutrition_confidence: Union[float, str]
    matched_ingredients: List[str]
    missing_ingredients: List[str]
    explanation: str

    model_config = ConfigDict(extra="ignore")


class RecommendationResponse(BaseModel):
    """Recommendation response envelope."""
    query: Dict[str, Any]
    count: int
    recommendations: List[RecommendationItem]
