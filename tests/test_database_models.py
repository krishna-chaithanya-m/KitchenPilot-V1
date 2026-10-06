"""Unit and integration tests for SQLAlchemy database models and schema definitions."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase

from src.db.base import Base
from src.db.models import (
    RecipeModel,
    IngredientModel,
    IngredientAliasModel,
    RecipeIngredientModel,
    RecipeNutritionModel,
    RecipeIngredientNutritionModel,
    DatasetManifestMetadataModel,
)


def test_models_registered_in_metadata():
    """Verify all 7 production models are registered in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "recipes",
        "ingredients",
        "ingredient_aliases",
        "recipe_ingredients",
        "recipe_nutrition",
        "recipe_ingredient_nutrition",
        "dataset_manifest_metadata",
    }
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"


def test_recipe_model_columns_and_constraints():
    """Verify RecipeModel primary key, required columns, and indexes."""
    table = RecipeModel.__table__
    assert table.c.recipe_id.primary_key
    assert not table.c.recipe_name.nullable
    assert table.c.instructions.nullable  # 6 recipes have null instructions

    index_names = {idx.name for idx in table.indexes}
    assert "ix_recipes_recipe_name" in index_names
    assert "ix_recipes_cuisine" in index_names
    assert "ix_recipes_diet_type" in index_names


def test_ingredient_model_columns_and_constraints():
    """Verify IngredientModel primary key and indexes."""
    table = IngredientModel.__table__
    assert table.c.ingredient_id.primary_key
    assert not table.c.canonical_name.nullable

    index_names = {idx.name for idx in table.indexes}
    assert "ix_ingredients_canonical_name" in index_names


def test_foreign_key_definitions():
    """Verify explicit referential integrity foreign keys."""
    # recipe_ingredients
    ri_fks = {fk.target_fullname for fk in RecipeIngredientModel.__table__.foreign_keys}
    assert "recipes.recipe_id" in ri_fks
    assert "ingredients.ingredient_id" in ri_fks

    # ingredient_aliases
    ia_fks = {fk.target_fullname for fk in IngredientAliasModel.__table__.foreign_keys}
    assert "ingredients.ingredient_id" in ia_fks

    # recipe_nutrition
    rn_fks = {fk.target_fullname for fk in RecipeNutritionModel.__table__.foreign_keys}
    assert "recipes.recipe_id" in rn_fks

    # recipe_ingredient_nutrition
    rin_fks = {fk.target_fullname for fk in RecipeIngredientNutritionModel.__table__.foreign_keys}
    assert "recipes.recipe_id" in rin_fks


def test_dataset_manifest_metadata_model():
    """Verify dataset manifest metadata table structure."""
    table = DatasetManifestMetadataModel.__table__
    assert table.c.id.primary_key
    assert not table.c.dataset_name.nullable
    assert not table.c.dataset_version.nullable
