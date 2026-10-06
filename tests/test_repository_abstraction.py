"""Tests for repository abstraction, factory, and CSV/Postgres contracts."""

import pytest
from src.data.repository import BaseRecipeStore, PostgresRecipeStore
from src.api.dependencies import RecipeStore, create_recipe_store, get_recipe_store
from src.db.config import DATA_BACKEND


def test_recipe_store_inherits_base_recipe_store():
    """Verify RecipeStore conforms to BaseRecipeStore interface."""
    assert issubclass(RecipeStore, BaseRecipeStore)
    assert issubclass(PostgresRecipeStore, BaseRecipeStore)


def test_factory_creates_csv_store_by_default(monkeypatch):
    """Verify create_recipe_store defaults to RecipeStore (CSV backend)."""
    monkeypatch.setenv("DATA_BACKEND", "csv")
    store = create_recipe_store()
    assert isinstance(store, RecipeStore)
    assert not isinstance(store, PostgresRecipeStore)


def test_factory_creates_postgres_store_when_configured(monkeypatch):
    """Verify create_recipe_store creates PostgresRecipeStore when DATA_BACKEND=postgres."""
    monkeypatch.setenv("DATA_BACKEND", "postgres")
    store = create_recipe_store()
    assert isinstance(store, PostgresRecipeStore)


def test_csv_store_implements_required_methods():
    """Verify CSV RecipeStore implements all abstract methods on BaseRecipeStore."""
    store = RecipeStore()
    assert hasattr(store, "exists")
    assert hasattr(store, "list_recipes")
    assert hasattr(store, "get_recipe")
    assert hasattr(store, "get_nutrition")
    assert hasattr(store, "get_recipe_ingredients")

    # Quick smoke test of CSV backend
    recipes, total, total_pages = store.list_recipes(page=1, page_size=5)
    assert len(recipes) == 5
    assert total > 6000
    first_id = recipes[0].recipe_id

    recipe = store.get_recipe(first_id)
    assert recipe is not None
    assert recipe.recipe_id == first_id

    nutrition = store.get_nutrition(first_id)
    assert nutrition is not None
    assert nutrition.recipe_id == first_id
