"""SQLAlchemy 2.x ORM models representing the KitchenPilot production catalog."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    DateTime,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class RecipeModel(Base):
    """Normalized recipe entity."""

    __tablename__ = "recipes"

    recipe_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    recipe_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    name_local: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cuisine: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    region: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    meal_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    ingredients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prep_time_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cook_time_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_time_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    servings: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    diet_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    vegetarian: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    vegan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    jain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    satvik: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    contains: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, default="M001")
    source_license: Mapped[str] = mapped_column(String(64), nullable=False, default="CC BY 4.0")

    # One-to-one relationship to nutrition
    nutrition: Mapped[Optional[RecipeNutritionModel]] = relationship(
        "RecipeNutritionModel", back_populates="recipe", uselist=False, cascade="all, delete-orphan"
    )

    # One-to-many relationship to recipe ingredients
    recipe_ingredients: Mapped[List[RecipeIngredientModel]] = relationship(
        "RecipeIngredientModel", back_populates="recipe", cascade="all, delete-orphan"
    )


class IngredientModel(Base):
    """Canonical ingredient ontology entity."""

    __tablename__ = "ingredients"

    ingredient_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    ingredient_form: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recipe_occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_variant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    mapping_status: Mapped[str] = mapped_column(String(64), nullable=False, default="VALIDATED_AUTO")
    vegetarian: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    vegan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allergen_flags: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    nutrition_reference: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    default_unit: Mapped[str] = mapped_column(String(32), nullable=False, default="g")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # One-to-many aliases
    aliases: Mapped[List[IngredientAliasModel]] = relationship(
        "IngredientAliasModel", back_populates="ingredient", cascade="all, delete-orphan"
    )


class IngredientAliasModel(Base):
    """Normalized ingredient alias mapping entity."""

    __tablename__ = "ingredient_aliases"

    alias_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    canonical_ingredient_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("ingredients.ingredient_id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    normalized_alias: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="VALIDATED", index=True)

    ingredient: Mapped[IngredientModel] = relationship("IngredientModel", back_populates="aliases")


class RecipeIngredientModel(Base):
    """Recipe-to-ingredient relational linkage."""

    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("recipes.recipe_id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_ingredient: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ingredient: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    preparation: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    ingredient_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("ingredients.ingredient_id", ondelete="SET NULL"), nullable=True, index=True
    )
    canonical_ingredient: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    ingredient_form: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mapping_status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mapping_source: Mapped[str] = mapped_column(String(64), nullable=False)

    recipe: Mapped[RecipeModel] = relationship("RecipeModel", back_populates="recipe_ingredients")

    __table_args__ = (
        Index("ix_recipe_ingredients_recipe_ing", "recipe_id", "ingredient_id"),
    )


class RecipeNutritionModel(Base):
    """Aggregated recipe nutrition profile."""

    __tablename__ = "recipe_nutrition"

    recipe_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("recipes.recipe_id", ondelete="CASCADE"), primary_key=True
    )
    recipe_name: Mapped[str] = mapped_column(String(512), nullable=False)
    servings: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_calories_kcal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_protein_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_fat_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_carbs_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_fiber_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_sugar_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_sodium_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    per_serving_calories_kcal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    per_serving_protein_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    per_serving_fat_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    per_serving_carbs_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    per_serving_fiber_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    per_serving_sugar_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    per_serving_sodium_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    nutrition_quality: Mapped[str] = mapped_column(String(32), nullable=False, default="PARTIAL", index=True)
    ingredient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calculated_ingredient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmapped_ingredient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_match_ingredient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_review_ingredient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qualitative_quantity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversion_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state_mismatch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    recipe: Mapped[RecipeModel] = relationship("RecipeModel", back_populates="nutrition")


class RecipeIngredientNutritionModel(Base):
    """Per-ingredient calculated nutrition breakdown."""

    __tablename__ = "recipe_ingredient_nutrition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("recipes.recipe_id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_ingredient: Mapped[str] = mapped_column(Text, nullable=False)
    ingredient: Mapped[str] = mapped_column(String(256), nullable=False)
    quantity: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    preparation: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    ingredient_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    canonical_ingredient: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    mapping_status: Mapped[str] = mapped_column(String(64), nullable=False)
    curation_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cnf_food_code: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cnf_food_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    parsed_quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity_parse_status: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    grams: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conversion_status: Mapped[str] = mapped_column(String(64), nullable=False)
    state_status: Mapped[str] = mapped_column(String(64), nullable=False)
    energy_kcal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fiber_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sugar_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sodium_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mapping_quality: Mapped[str] = mapped_column(String(64), nullable=False)
    nutrition_quality: Mapped[str] = mapped_column(String(64), nullable=False)
    nutrition_source: Mapped[str] = mapped_column(String(64), nullable=False)
    calculation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DatasetManifestMetadataModel(Base):
    """Database audit and provenance metadata tracking imported dataset versions."""

    __tablename__ = "dataset_manifest_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    import_status: Mapped[str] = mapped_column(String(64), nullable=False, default="SUCCESS")
