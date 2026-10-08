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


def test_qualitative_feedback_and_personalization_models():
    """Verify qualitative feedback and user models are registered and structurally sound."""
    from src.personalization.models import QualitativeFeedbackModel, UserModel
    table = QualitativeFeedbackModel.__table__
    assert table.c.id.primary_key
    assert not table.c.user_id.nullable
    assert not table.c.issue_type.nullable
    user_fks = {fk.target_fullname for fk in table.foreign_keys}
    assert "users.id" in user_fks
    assert "recipes.recipe_id" in user_fks


def test_alembic_migration_chain_is_linear():
    """Verify that Alembic migrations form an unbroken linear revision chain."""
    from pathlib import Path
    import importlib.util

    versions_dir = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    migration_files = list(versions_dir.glob("*.py"))
    assert len(migration_files) >= 3

    revisions = {}
    down_revisions = {}
    for mf in migration_files:
        if mf.name.startswith("__"):
            continue
        spec = importlib.util.spec_from_file_location(mf.stem, mf)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rev = getattr(mod, "revision", None)
        down = getattr(mod, "down_revision", None)
        if rev:
            revisions[rev] = mf.name
            down_revisions[rev] = down

    # Verify head is 003_qualitative_feedback_schema and down revision chain leads back to None
    curr = "003_qualitative_feedback_schema"
    assert curr in revisions
    visited = []
    while curr is not None:
        visited.append(curr)
        curr = down_revisions.get(curr)

    assert visited == [
        "003_qualitative_feedback_schema",
        "9ee7090d2edc",
        "002_user_personalization_schema",
        "001_initial_schema",
    ]
