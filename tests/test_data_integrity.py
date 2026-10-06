"""Tests for relational referential integrity, data versioning, and manifests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.contracts import validate_cross_dataset_integrity


def test_data_version_file():
    version_file = Path("data/VERSION")
    assert version_file.exists(), "data/VERSION file is missing"
    content = version_file.read_text().strip()
    assert content == "0.1.0", f"Unexpected data version: {content}"


def test_manifest_files_exist_and_valid():
    manifest_dir = Path("data/manifests")
    expected = [
        "recipe_dataset_manifest.json",
        "nutrition_dataset_manifest.json",
        "ingredient_manifest.json",
        "production_data_manifest.json",
    ]
    for fn in expected:
        p = manifest_dir / fn
        assert p.exists(), f"Missing manifest: {fn}"
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert "status" in data or "stage" in data


def test_cross_dataset_referential_integrity_live():
    rec = pd.read_csv("data/processed/recipes.csv", low_memory=False)
    nut = pd.read_csv("data/processed/recipe_nutrition.csv", low_memory=False)
    ring = pd.read_csv("data/processed/recipe_ingredients_linked.csv", low_memory=False)
    ing = pd.read_csv("data/processed/ingredients.csv", low_memory=False)
    alias = pd.read_csv("data/mappings/ingredients/ingredient_aliases.csv", low_memory=False)

    res = validate_cross_dataset_integrity(rec, nut, ing, ring, alias)
    assert res.is_valid, f"Referential integrity failure: {res.errors}"
    assert len(res.errors) == 0


def test_no_duplicate_primary_keys():
    rec = pd.read_csv("data/processed/recipes.csv", low_memory=False)
    nut = pd.read_csv("data/processed/recipe_nutrition.csv", low_memory=False)
    ing = pd.read_csv("data/processed/ingredients.csv", low_memory=False)
    alias = pd.read_csv("data/mappings/ingredients/ingredient_aliases.csv", low_memory=False)

    assert rec["recipe_id"].duplicated().sum() == 0, "Duplicate recipe_id in recipes.csv"
    assert nut["recipe_id"].duplicated().sum() == 0, "Duplicate recipe_id in recipe_nutrition.csv"
    assert ing["ingredient_id"].duplicated().sum() == 0, "Duplicate ingredient_id in ingredients.csv"
    assert alias["alias_id"].duplicated().sum() == 0, "Duplicate alias_id in ingredient_aliases.csv"
