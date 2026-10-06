"""Benchmark and Performance Evaluation for Stage E Constraint Engine.

Measures:
1. Canonical ingredient resolution latency
2. Hard filtering latency (allergen, dietary, ingredient)
3. Nutrition boundary filtering latency
4. Complete candidate evaluation across all 6,871 recipes
5. Candidate filtering latency
"""

from __future__ import annotations

import time
from pathlib import Path
import pandas as pd

from src.constraints import (
    AllergenConstraints,
    ConstraintEngine,
    ConstraintRequest,
    DietaryConstraints,
    IngredientConstraints,
    NutritionConstraints,
)


def run_benchmark():
    print("=" * 70)
    print("STAGE E — CONSTRAINT ENGINE PERFORMANCE BENCHMARK")
    print("=" * 70)

    engine = ConstraintEngine()
    recipes_df = pd.read_csv("data/processed/recipes.csv")
    all_recipe_ids = [str(r).strip() for r in recipes_df["recipe_id"]]
    total_recipes = len(all_recipe_ids)
    print(f"Catalog size: {total_recipes} recipes")

    # 1. Ingredient Resolution Benchmark
    sample_queries = [
        "ING00046", "cumin", "jeera", "Fresh Cumin Seeds", "onion", "garlic",
        "red chilli powder", "paneer", "milk", "spinach", "unknown_spice_123"
    ]
    t0 = time.perf_counter()
    n_queries = 1000
    for i in range(n_queries):
        q = sample_queries[i % len(sample_queries)]
        engine.ingredient_matcher.resolve_ingredient(q)
    t_res = (time.perf_counter() - t0) * 1000 / n_queries
    print(f"1. Ingredient resolution latency: {t_res:.4f} ms per lookup ({n_queries} iterations)")

    # 2. Hard Dietary Filtering Benchmark across all 6,871 recipes
    req_diet = ConstraintRequest(dietary=DietaryConstraints(vegetarian=True))
    t0 = time.perf_counter()
    veg_pass = 0
    for rid in all_recipe_ids:
        passed, _, _ = engine.dietary_engine.evaluate_dietary_compliance(rid, req_diet.dietary)
        if passed:
            veg_pass += 1
    t_diet = (time.perf_counter() - t0) * 1000
    print(f"2. Dietary compliance evaluation (6,871 recipes): {t_diet:.2f} ms total ({t_diet / total_recipes:.4f} ms/recipe) [Passed: {veg_pass}]")

    # 3. Allergen Exclusion Benchmark across all 6,871 recipes
    req_allg = AllergenConstraints(excluded_allergens=["dairy", "peanut"])
    t0 = time.perf_counter()
    allg_pass = 0
    for rid in all_recipe_ids:
        passed, _, _ = engine.dietary_engine.evaluate_allergen_exclusions(rid, req_allg)
        if passed:
            allg_pass += 1
    t_allg = (time.perf_counter() - t0) * 1000
    print(f"3. Allergen exclusion evaluation (6,871 recipes): {t_allg:.2f} ms total ({t_allg / total_recipes:.4f} ms/recipe) [Passed: {allg_pass}]")

    # 4. Nutrition Filtering Benchmark across all 6,871 recipes
    req_nut = NutritionConstraints(max_calories=500.0, min_protein_g=10.0)
    t0 = time.perf_counter()
    nut_pass = 0
    for rid in all_recipe_ids:
        passed, _, _, _ = engine.nutrition_evaluator.evaluate_nutrition_constraints(rid, req_nut)
        if passed:
            nut_pass += 1
    t_nut = (time.perf_counter() - t0) * 1000
    print(f"4. Nutrition limits evaluation (6,871 recipes): {t_nut:.2f} ms total ({t_nut / total_recipes:.4f} ms/recipe) [Passed: {nut_pass}]")

    # 5. Full Constraint Engine Candidate Filtering (Complete Pipeline)
    full_req = ConstraintRequest(
        dietary=DietaryConstraints(vegetarian=True),
        allergens=AllergenConstraints(excluded_allergens=["peanut"]),
        ingredients=IngredientConstraints(
            excluded_ingredients=["onion", "garlic"],
            available_ingredients=["potato", "tomato", "cumin", "turmeric"],
            require_all_ingredients=False,
        ),
        nutrition=NutritionConstraints(max_calories=600.0),
    )

    t0 = time.perf_counter()
    eligible, evals, diag = engine.filter_candidates(all_recipe_ids, full_req)
    t_full = (time.perf_counter() - t0) * 1000
    print(f"5. Full pipeline candidate filtering (6,871 recipes): {t_full:.2f} ms ({t_full / total_recipes:.4f} ms/recipe)")
    print(f"   Eligible: {len(eligible)} / {total_recipes}")
    print(f"   Diagnostics: {diag}")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
