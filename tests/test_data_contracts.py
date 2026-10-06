"""Tests for production data schemas and dataset contracts."""

from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from src.data.contracts import (
    validate_ingredient_aliases_dataset,
    validate_ingredient_dataset,
    validate_recipe_dataset,
    validate_recipe_ingredient_links,
    validate_recipe_ingredient_nutrition_dataset,
    validate_recipe_nutrition_dataset,
)
from src.data.schemas import (
    CanonicalIngredientSchema,
    IngredientAliasSchema,
    RecipeIngredientLinkedSchema,
    RecipeNutritionSchema,
    RecipeSchema,
)


def test_recipe_schema_validation_valid():
    data = {
        "recipe_id": "R00001",
        "recipe_name": "Test Masala",
        "prep_time_min": 15,
        "cook_time_min": 30,
        "total_time_min": 45,
        "servings": 4,
        "vegetarian": True,
        "vegan": False,
        "jain": False,
        "satvik": False,
    }
    rec = RecipeSchema(**data)
    assert rec.recipe_id == "R00001"
    assert rec.servings == 4
    assert rec.vegetarian is True


def test_recipe_schema_validation_invalid_id():
    data = {
        "recipe_id": "INVALID123",
        "recipe_name": "Bad ID Recipe",
        "servings": 2,
    }
    with pytest.raises(ValidationError):
        RecipeSchema(**data)


def test_recipe_schema_validation_coercion():
    data = {
        "recipe_id": "R00002",
        "recipe_name": "Coerced Recipe",
        "prep_time_min": "10",
        "servings": "3",
        "vegetarian": "true",
    }
    rec = RecipeSchema(**data)
    assert rec.prep_time_min == 10
    assert rec.servings == 3
    assert rec.vegetarian is True


def test_canonical_ingredient_schema():
    data = {
        "ingredient_id": "ING00083",
        "canonical_name": "onion",
        "display_name": "Onion",
        "ingredient_form": "default",
        "category": "vegetable",
        "recipe_occurrence_count": 1972,
        "candidate_variant_count": 1,
        "source": "Indian recipe corpus",
        "mapping_status": "VALIDATED_AUTO",
    }
    ing = CanonicalIngredientSchema(**data)
    assert ing.ingredient_id == "ING00083"


def test_canonical_ingredient_schema_invalid_id():
    data = {
        "ingredient_id": "BAD_ID",
        "canonical_name": "onion",
        "display_name": "Onion",
        "category": "vegetable",
        "source": "manual",
        "mapping_status": "AUTO",
    }
    with pytest.raises(ValidationError):
        CanonicalIngredientSchema(**data)


def test_ingredient_alias_schema():
    data = {
        "alias_id": "ALIAS00001",
        "canonical_ingredient_id": "ING00083",
        "alias": "onions",
        "normalized_alias": "onion",
        "source": "recipe_corpus",
        "confidence": 1.0,
        "review_status": "VALIDATED",
    }
    alias = IngredientAliasSchema(**data)
    assert alias.alias_id == "ALIAS00001"
    assert alias.review_status == "VALIDATED"


def test_ingredient_alias_schema_invalid_status():
    data = {
        "alias_id": "ALIAS00001",
        "canonical_ingredient_id": "ING00083",
        "alias": "onions",
        "normalized_alias": "onion",
        "source": "recipe_corpus",
        "confidence": 1.0,
        "review_status": "UNKNOWN_STATUS",
    }
    with pytest.raises(ValidationError):
        IngredientAliasSchema(**data)


def test_recipe_dataset_contract_live():
    df = pd.read_csv("data/processed/recipes.csv", low_memory=False)
    res = validate_recipe_dataset(df)
    assert res.is_valid, f"Recipe contract failed: {res.errors}"
    assert res.valid_records == 6871


def test_ingredient_dataset_contract_live():
    df = pd.read_csv("data/processed/ingredients.csv", low_memory=False)
    res = validate_ingredient_dataset(df)
    assert res.is_valid, f"Ingredient contract failed: {res.errors}"
    assert res.valid_records == 129


def test_recipe_nutrition_dataset_contract_live():
    df = pd.read_csv("data/processed/recipe_nutrition.csv", low_memory=False)
    res = validate_recipe_nutrition_dataset(df)
    assert res.is_valid, f"Nutrition contract failed: {res.errors}"
    assert res.valid_records == 6871


def test_ingredient_aliases_dataset_contract_live():
    df = pd.read_csv("data/mappings/ingredients/ingredient_aliases.csv", low_memory=False)
    res = validate_ingredient_aliases_dataset(df)
    assert res.is_valid, f"Alias contract failed: {res.errors}"
    assert res.valid_records == len(df)


# ---------------------------------------------------------------------------
# Recipe Title Cleaning Regression & Negative Tests
# ---------------------------------------------------------------------------
from src.cleaning.normalize_recipes import clean_recipe_title


@pytest.mark.parametrize(
    "input_title,expected_title",
    [
        (
            "One Pot Vegetable Biryani Recipe In Preethi Electric Pressure Cooker",
            "One Pot Vegetable Biryani Recipe",
        ),
        (
            "One Pot Pav Bhaji Recipe Using Preethi Electric Pressure Cooker",
            "One Pot Pav Bhaji Recipe",
        ),
        (
            "Classic Cheesecake Recipe With Lemon Curd Made Using Preethi Electric Pressure Cooker",
            "Classic Cheesecake Recipe With Lemon Curd",
        ),
        (
            "Jaipuri Potato Onion Vegetable Recipe Using Preeti Electric Pressure Cooker",
            "Jaipuri Potato Onion Vegetable Recipe",
        ),
        (
            "Creamy & Delicious Egg Mayo Sandwich Recipe - Kids Recipes Made With Del Monte",
            "Creamy & Delicious Egg Mayo Sandwich Recipe",
        ),
        (
            "No Onion No Garlic Lobia Masala Recipe In Electric Pressure Cooker",
            "No Onion No Garlic Lobia Masala Recipe",
        ),
        (
            "Desi Style Masala Pasta Recipe Using Electric Pressure Cooker",
            "Desi Style Masala Pasta Recipe",
        ),
    ],
)
def test_clean_recipe_title_regression(input_title, expected_title):
    """Verify promotional appliance and sponsor clauses are cleanly removed."""
    assert clean_recipe_title(input_title) == expected_title


@pytest.mark.parametrize(
    "culinary_title",
    [
        "Tawa Pulao",
        "Tawa Paratha Recipe",
        "Kadai Paneer",
        "Kadai Mushroom Gravy Recipe",
        "Karahi Gosht",
        "Handi Biryani",
        "Matka recipe",
        "Pigeon Peas Curry Recipe",
        "Pressure Cooker Cake Recipe",
    ],
)
def test_clean_recipe_title_negative_preservation(culinary_title):
    """Verify legitimate culinary vessels, ingredients, and traditional styles remain unchanged."""
    assert clean_recipe_title(culinary_title) == culinary_title


def test_r04349_cleaned_in_processed_dataset():
    """Verify R04349 in live recipes.csv has cleaned display title."""
    df = pd.read_csv("data/processed/recipes.csv", low_memory=False)
    r = df[df["recipe_id"] == "R04349"]
    assert len(r) == 1, "R04349 not found in recipes.csv"
    assert r.iloc[0]["recipe_name"] == "One Pot Vegetable Biryani Recipe"
    assert r.iloc[0]["name_local"] == "One Pot Vegetable Biryani Recipe"

