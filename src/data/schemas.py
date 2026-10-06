"""Formal Pydantic schemas for KitchenPilot production data architecture."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


def _coerce_optional_str(v: Any) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return str(v).strip()


def _coerce_optional_float(v: Any) -> Optional[float]:
    if v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(v)


class RecipeSchema(BaseModel):
    """Schema contract for normalized recipe records."""

    recipe_id: str = Field(..., description="Unique recipe identifier (e.g. R00001)")
    recipe_name: str = Field(..., min_length=1, description="Primary recipe title")
    name_local: Optional[str] = Field(default="", description="Original/local recipe title")
    cuisine: Optional[str] = Field(default="", description="Cuisine classification")
    region: Optional[str] = Field(default="", description="Geographical culinary region")
    meal_type: Optional[str] = Field(default="", description="Meal course or type")
    category: Optional[str] = Field(default="", description="Recipe category")
    ingredients: Optional[str] = Field(default="", description="Raw comma-separated ingredients text")
    instructions: Optional[str] = Field(default="", description="Step-by-step cooking instructions")
    prep_time_min: int = Field(default=0, ge=0, description="Preparation time in minutes")
    cook_time_min: int = Field(default=0, ge=0, description="Cooking time in minutes")
    total_time_min: int = Field(default=0, ge=0, description="Total time in minutes")
    servings: int = Field(..., ge=1, description="Yield serving count")
    diet_type: Optional[str] = Field(default="", description="Diet classification string")
    vegetarian: bool = Field(default=False, description="Vegetarian diet indicator")
    vegan: bool = Field(default=False, description="Vegan diet indicator")
    jain: bool = Field(default=False, description="Jain dietary indicator")
    satvik: bool = Field(default=False, description="Satvik dietary indicator")
    contains: Optional[str] = Field(default="", description="Allergen declaration")
    calories_kcal: Optional[float] = Field(default=None, description="Caloric energy")
    protein_g: Optional[float] = Field(default=None, description="Protein in grams")
    carbs_g: Optional[float] = Field(default=None, description="Carbohydrates in grams")
    fat_g: Optional[float] = Field(default=None, description="Fat in grams")
    fiber_g: Optional[float] = Field(default=None, description="Fiber in grams")
    source_id: str = Field(default="M001", description="Original dataset source identifier")
    source_license: str = Field(default="CC BY 4.0", description="Dataset copyright license")

    @field_validator("recipe_id")
    @classmethod
    def validate_recipe_id(cls, v: str) -> str:
        if not re.match(r"^R\d{5}$", v):
            raise ValueError(f"Invalid recipe_id format: '{v}'. Expected format 'R' followed by 5 digits.")
        return v

    @field_validator(
        "name_local", "cuisine", "region", "meal_type", "category",
        "ingredients", "instructions", "diet_type", "contains",
        mode="before"
    )
    @classmethod
    def clean_optional_strings(cls, v: Any) -> str:
        return _coerce_optional_str(v)

    @field_validator("calories_kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", mode="before")
    @classmethod
    def clean_optional_floats(cls, v: Any) -> Optional[float]:
        val = _coerce_optional_float(v)
        if val is not None and val < 0:
            raise ValueError(f"Numeric nutrition field cannot be negative: {val}")
        return val

    @field_validator("prep_time_min", "cook_time_min", "total_time_min", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> int:
        if v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
            return 0
        return int(float(v))

    @field_validator("servings", mode="before")
    @classmethod
    def coerce_servings(cls, v: Any) -> int:
        if v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
            return 1
        val = int(float(v))
        return max(1, val)

    @field_validator("vegetarian", "vegan", "jain", "satvik", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes", "t")
        return bool(v)


class CanonicalIngredientSchema(BaseModel):
    """Schema contract for canonical ingredients."""

    ingredient_id: str = Field(..., description="Canonical ingredient identifier (e.g. ING00001)")
    canonical_name: str = Field(..., min_length=1, description="Standardized canonical name")
    display_name: str = Field(..., min_length=1, description="User-facing display name")
    ingredient_form: str = Field(default="default", description="Form of ingredient (whole, powder, etc.)")
    category: str = Field(..., min_length=1, description="Culinary category")
    recipe_occurrence_count: int = Field(default=0, ge=0, description="Frequency in recipe corpus")
    candidate_variant_count: int = Field(default=0, ge=0, description="Number of mapped candidate variants")
    source: str = Field(..., description="Provenance / derivation source")
    mapping_status: str = Field(..., description="Validation status")

    @field_validator("ingredient_id")
    @classmethod
    def validate_ingredient_id(cls, v: str) -> str:
        if not re.match(r"^ING\d{5}$", v):
            raise ValueError(f"Invalid ingredient_id format: '{v}'. Expected 'ING' followed by 5 digits.")
        return v


class RecipeIngredientLinkedSchema(BaseModel):
    """Schema contract for recipe-ingredient links."""

    recipe_id: str = Field(..., description="Foreign key to recipe")
    original_ingredient: str = Field(..., min_length=1, description="Raw ingredient line from recipe")
    quantity: Optional[str] = Field(default="", description="Extracted quantity string")
    unit: Optional[str] = Field(default="", description="Extracted unit string")
    ingredient: Optional[str] = Field(default="", description="Cleaned ingredient name")
    preparation: Optional[str] = Field(default="", description="Extracted culinary preparation state")
    ingredient_id: Optional[str] = Field(default=None, description="Foreign key to canonical ingredient")
    canonical_ingredient: Optional[str] = Field(default=None, description="Canonical name")
    display_name: Optional[str] = Field(default=None, description="Display name")
    ingredient_form: Optional[str] = Field(default=None, description="Ingredient form")
    category: Optional[str] = Field(default=None, description="Ingredient category")
    mapping_status: str = Field(..., description="Mapping status (MAPPED_CANONICAL, MAPPED_VALIDATED, REVIEW)")
    mapping_source: str = Field(..., description="Source of mapping linkage")

    @field_validator("recipe_id")
    @classmethod
    def validate_recipe_id(cls, v: str) -> str:
        if not re.match(r"^R\d{5}$", v):
            raise ValueError(f"Invalid recipe_id: '{v}'. Expected 'R' followed by 5 digits.")
        return v

    @field_validator("quantity", "unit", "ingredient", "preparation", mode="before")
    @classmethod
    def clean_optional_strings(cls, v: Any) -> str:
        return _coerce_optional_str(v)

    @field_validator("ingredient_id", "canonical_ingredient", "display_name", "ingredient_form", "category", mode="before")
    @classmethod
    def clean_nullable_strings(cls, v: Any) -> Optional[str]:
        s = _coerce_optional_str(v)
        return s if s else None

    @field_validator("ingredient_id")
    @classmethod
    def validate_ingredient_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "":
            if not re.match(r"^ING\d{5}$", v):
                raise ValueError(f"Invalid ingredient_id in link: '{v}'. Expected 'ING' followed by 5 digits.")
        return v


class RecipeNutritionSchema(BaseModel):
    """Schema contract for aggregated recipe nutrition."""

    recipe_id: str = Field(..., description="Unique recipe identifier")
    recipe_name: str = Field(..., min_length=1, description="Recipe title")
    servings: int = Field(..., ge=1, description="Serving count")
    total_calories_kcal: float = Field(..., ge=0, description="Total caloric energy")
    total_protein_g: float = Field(..., ge=0, description="Total protein in grams")
    total_fat_g: float = Field(..., ge=0, description="Total fat in grams")
    total_carbs_g: float = Field(..., ge=0, description="Total carbohydrates in grams")
    total_fiber_g: float = Field(..., ge=0, description="Total dietary fiber in grams")
    total_sugar_g: float = Field(..., ge=0, description="Total sugar in grams")
    total_sodium_mg: float = Field(..., ge=0, description="Total sodium in milligrams")
    per_serving_calories_kcal: float = Field(..., ge=0, description="Per-serving calories")
    per_serving_protein_g: float = Field(..., ge=0, description="Per-serving protein")
    per_serving_fat_g: float = Field(..., ge=0, description="Per-serving fat")
    per_serving_carbs_g: float = Field(..., ge=0, description="Per-serving carbohydrates")
    per_serving_fiber_g: float = Field(..., ge=0, description="Per-serving fiber")
    per_serving_sugar_g: float = Field(..., ge=0, description="Per-serving sugar")
    per_serving_sodium_mg: float = Field(..., ge=0, description="Per-serving sodium")
    nutrition_quality: str = Field(..., description="Quality tier (COMPLETE, PARTIAL, APPROXIMATE)")
    ingredient_count: int = Field(..., ge=0, description="Total ingredients in recipe")
    calculated_ingredient_count: int = Field(..., ge=0, description="Ingredients with calculated nutrition")
    unmapped_ingredient_count: int = Field(..., ge=0, description="Unmapped ingredients")
    no_match_ingredient_count: int = Field(..., ge=0, description="Ingredients with no CNF match")
    needs_review_ingredient_count: int = Field(..., ge=0, description="Ingredients needing review")
    qualitative_quantity_count: int = Field(..., ge=0, description="Qualitative quantities (e.g. to taste)")
    conversion_failure_count: int = Field(..., ge=0, description="Failed unit conversions")
    state_mismatch_count: int = Field(..., ge=0, description="State mismatches (raw vs cooked)")

    @field_validator("recipe_id")
    @classmethod
    def validate_recipe_id(cls, v: str) -> str:
        if not re.match(r"^R\d{5}$", v):
            raise ValueError(f"Invalid recipe_id: '{v}'.")
        return v

    @field_validator("nutrition_quality")
    @classmethod
    def validate_quality(cls, v: str) -> str:
        allowed = {"COMPLETE", "PARTIAL", "APPROXIMATE"}
        if v not in allowed:
            raise ValueError(f"Invalid nutrition_quality: '{v}'. Expected one of {allowed}.")
        return v


class RecipeIngredientNutritionSchema(BaseModel):
    """Schema contract for per-ingredient nutrition breakdown."""

    recipe_id: str = Field(..., description="Unique recipe identifier")
    original_ingredient: str = Field(..., min_length=1, description="Raw ingredient text")
    ingredient: str = Field(..., description="Cleaned ingredient name")
    quantity: Optional[str] = Field(default="", description="Original quantity string")
    unit: Optional[str] = Field(default="", description="Original unit string")
    preparation: Optional[str] = Field(default="", description="Preparation state")
    ingredient_id: Optional[str] = Field(default=None, description="Canonical ingredient identifier")
    canonical_ingredient: Optional[str] = Field(default=None, description="Canonical ingredient name")
    mapping_status: str = Field(..., description="Mapping status")
    curation_status: Optional[str] = Field(default=None, description="CNF curation status")
    cnf_food_code: Optional[float] = Field(default=None, description="CNF food code")
    cnf_food_name: Optional[str] = Field(default=None, description="CNF food description")
    parsed_quantity: Optional[float] = Field(default=None, ge=0, description="Parsed numeric quantity")
    quantity_parse_status: str = Field(..., description="Quantity parse status")
    normalized_unit: Optional[str] = Field(default=None, description="Standardized unit (g, ml, cup, etc.)")
    grams: Optional[float] = Field(default=None, ge=0, description="Mass in grams")
    conversion_status: str = Field(..., description="Unit conversion status")
    state_status: str = Field(..., description="Cooked state status")
    energy_kcal: float = Field(..., ge=0, description="Energy in kcal")
    protein_g: float = Field(..., ge=0, description="Protein in grams")
    fat_g: float = Field(..., ge=0, description="Fat in grams")
    carbs_g: float = Field(..., ge=0, description="Carbohydrates in grams")
    fiber_g: float = Field(..., ge=0, description="Fiber in grams")
    sugar_g: float = Field(..., ge=0, description="Sugar in grams")
    sodium_mg: float = Field(..., ge=0, description="Sodium in mg")
    mapping_quality: str = Field(..., description="Mapping quality assessment")
    nutrition_quality: str = Field(..., description="Nutrition quality assessment")
    nutrition_source: str = Field(..., description="Source of nutrition factors")
    calculation_notes: str = Field(default="", description="Audit trail notes")

    @field_validator("quantity", "unit", "preparation", "calculation_notes", mode="before")
    @classmethod
    def clean_optional_strings(cls, v: Any) -> str:
        return _coerce_optional_str(v)

    @field_validator("ingredient_id", "canonical_ingredient", "curation_status", "cnf_food_name", "normalized_unit", mode="before")
    @classmethod
    def clean_nullable_strings(cls, v: Any) -> Optional[str]:
        s = _coerce_optional_str(v)
        return s if s else None

    @field_validator("cnf_food_code", "parsed_quantity", "grams", mode="before")
    @classmethod
    def clean_nullable_floats(cls, v: Any) -> Optional[float]:
        return _coerce_optional_float(v)


class IngredientAliasSchema(BaseModel):
    """Schema contract for normalized ingredient alias mappings."""

    alias_id: str = Field(..., description="Unique alias identifier (e.g. ALIAS00001)")
    canonical_ingredient_id: str = Field(..., description="Foreign key to canonical ingredient (e.g. ING00001)")
    alias: str = Field(..., min_length=1, description="Raw or variant alias text")
    normalized_alias: str = Field(..., min_length=1, description="Standardized lookup key")
    source: str = Field(..., min_length=1, description="Origin of alias mapping")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score in [0.0, 1.0]")
    review_status: str = Field(..., description="Curation review status")

    @field_validator("alias_id")
    @classmethod
    def validate_alias_id(cls, v: str) -> str:
        if not re.match(r"^ALIAS\d{5}$", v):
            raise ValueError(f"Invalid alias_id: '{v}'. Expected 'ALIAS' followed by 5 digits.")
        return v

    @field_validator("canonical_ingredient_id")
    @classmethod
    def validate_canonical_id(cls, v: str) -> str:
        if not re.match(r"^ING\d{5}$", v):
            raise ValueError(f"Invalid canonical_ingredient_id: '{v}'. Expected 'ING' followed by 5 digits.")
        return v

    @field_validator("review_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"AUTO", "VALIDATED", "REVIEW_REQUIRED", "REJECTED"}
        if v not in allowed:
            raise ValueError(f"Invalid review_status: '{v}'. Expected one of {allowed}.")
        return v
