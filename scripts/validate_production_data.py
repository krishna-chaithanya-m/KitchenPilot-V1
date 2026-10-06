"""Unified Production Data Architecture Validation Entry Point for KitchenPilot.

Executes sequential contract checks:
1. Recipe validation
2. Canonical Ingredient validation
3. Recipe-Ingredient relationship validation
4. Recipe Nutrition validation
5. Recipe-Ingredient Nutrition validation
6. Ingredient Aliases validation
7. Cross-Dataset Referential Integrity validation

Exits 0 on total success, 1 on any critical contract failure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
os.chdir(ROOT_DIR)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from src.data.contracts import (
    validate_cross_dataset_integrity,
    validate_ingredient_aliases_dataset,
    validate_ingredient_dataset,
    validate_recipe_dataset,
    validate_recipe_ingredient_links,
    validate_recipe_ingredient_nutrition_dataset,
    validate_recipe_nutrition_dataset,
)


def main() -> int:
    print("=" * 70)
    print("KITCHENPILOT PRODUCTION DATA ARCHITECTURE VALIDATION PIPELINE")
    print("=" * 70)

    # File paths
    recipes_path = Path("data/processed/recipes.csv")
    ingredients_path = Path("data/processed/ingredients.csv")
    links_path = Path("data/processed/recipe_ingredients_linked.csv")
    nutrition_path = Path("data/processed/recipe_nutrition.csv")
    ring_nutrition_path = Path("data/processed/recipe_ingredient_nutrition.csv")
    aliases_path = Path("data/mappings/ingredients/ingredient_aliases.csv")

    paths = [
        recipes_path, ingredients_path, links_path,
        nutrition_path, ring_nutrition_path, aliases_path
    ]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print(f"[FAIL] Missing dataset file(s): {', '.join(missing)}")
        return 1

    print("\nLoading production dataset artifacts into memory...")
    rec_df = pd.read_csv(recipes_path, low_memory=False)
    ing_df = pd.read_csv(ingredients_path, low_memory=False)
    links_df = pd.read_csv(links_path, low_memory=False)
    nut_df = pd.read_csv(nutrition_path, low_memory=False)
    ring_nut_df = pd.read_csv(ring_nutrition_path, low_memory=False)
    alias_df = pd.read_csv(aliases_path, low_memory=False)
    print(f"Loaded: {len(rec_df):,} recipes, {len(ing_df):,} ingredients, {len(links_df):,} links, "
          f"{len(nut_df):,} recipe nutrition, {len(ring_nut_df):,} ingredient nutrition, {len(alias_df):,} aliases.\n")

    failures = []

    # 1. Recipe validation
    print("1. Running Recipe Dataset Validation...")
    res_rec = validate_recipe_dataset(rec_df)
    print(f"   {res_rec.summary()}")
    for w in res_rec.warnings:
        print(f"   [WARN] {w}")
    if not res_rec.is_valid:
        failures.append("Recipe Dataset Contract")
        for e in res_rec.errors:
            print(f"   [ERROR] {e}")

    # 2. Ingredient validation
    print("\n2. Running Canonical Ingredient Validation...")
    res_ing = validate_ingredient_dataset(ing_df)
    print(f"   {res_ing.summary()}")
    for w in res_ing.warnings:
        print(f"   [WARN] {w}")
    if not res_ing.is_valid:
        failures.append("Canonical Ingredient Contract")
        for e in res_ing.errors:
            print(f"   [ERROR] {e}")

    # 3. Recipe-ingredient relationship validation
    print("\n3. Running Recipe-Ingredient Relationship Validation...")
    res_links = validate_recipe_ingredient_links(links_df)
    print(f"   {res_links.summary()}")
    for w in res_links.warnings:
        print(f"   [WARN] {w}")
    if not res_links.is_valid:
        failures.append("Recipe-Ingredient Relationship Contract")
        for e in res_links.errors:
            print(f"   [ERROR] {e}")

    # 4. Nutrition validation
    print("\n4. Running Recipe Nutrition Validation...")
    res_nut = validate_recipe_nutrition_dataset(nut_df)
    print(f"   {res_nut.summary()}")
    for w in res_nut.warnings:
        print(f"   [WARN] {w}")
    if not res_nut.is_valid:
        failures.append("Recipe Nutrition Contract")
        for e in res_nut.errors:
            print(f"   [ERROR] {e}")

    print("\n5. Running Per-Ingredient Nutrition Validation...")
    res_ring_nut = validate_recipe_ingredient_nutrition_dataset(ring_nut_df)
    print(f"   {res_ring_nut.summary()}")
    for w in res_ring_nut.warnings:
        print(f"   [WARN] {w}")
    if not res_ring_nut.is_valid:
        failures.append("Per-Ingredient Nutrition Contract")
        for e in res_ring_nut.errors:
            print(f"   [ERROR] {e}")

    print("\n6. Running Ingredient Alias Validation...")
    res_alias = validate_ingredient_aliases_dataset(alias_df)
    print(f"   {res_alias.summary()}")
    for w in res_alias.warnings:
        print(f"   [WARN] {w}")
    if not res_alias.is_valid:
        failures.append("Ingredient Alias Contract")
        for e in res_alias.errors:
            print(f"   [ERROR] {e}")

    # 7. Cross-dataset integrity validation
    print("\n7. Running Cross-Dataset Referential Integrity Validation...")
    res_cross = validate_cross_dataset_integrity(rec_df, nut_df, ing_df, links_df, alias_df)
    print(f"   {res_cross.summary()}")
    for w in res_cross.warnings:
        print(f"   [WARN] {w}")
    if not res_cross.is_valid:
        failures.append("Cross-Dataset Referential Integrity Contract")
        for e in res_cross.errors:
            print(f"   [ERROR] {e}")

    # Summary
    print("\n" + "=" * 70)
    if failures:
        print(f"VALIDATION FAILED ({len(failures)} contract failure(s): {', '.join(failures)})")
        print("=" * 70)
        return 1
    else:
        print("ALL PRODUCTION DATA CONTRACTS PASSED (7/7 CHECKS SUCCESSFUL)")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(main())
