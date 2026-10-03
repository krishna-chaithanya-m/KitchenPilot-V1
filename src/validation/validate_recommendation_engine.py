"""Validation Suite for KitchenPilot-V1 Recommendation Engine.

Executes automated validation checks:
1. Determinism
2. Deduplication
3. Self-exclusion
4. Score range boundedness [0, 1]
5. Strict ranking monotonicity
6. Hard dietary filters
7. Excluded ingredients enforcement
8. Required ingredients enforcement
9. Empty ingredient handling
10. Unknown ingredient resilience
11. Unavailable nutrition handling
12. Top-k handling
13. No division-by-zero
14. No NaN or infinite values
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.recommendation import (
    KitchenPilotRecommender,
    NutritionGoals,
    RecommendationConfig,
    UserPreferences,
)


def validate_recommendation_engine() -> Dict[str, bool]:
    """Execute all validation checks and return results dict."""
    config = RecommendationConfig()
    recommender = KitchenPilotRecommender(config)
    results: Dict[str, bool] = {}

    print("=" * 60)
    print("KitchenPilot-V1: Validating Recommendation Engine")
    print("=" * 60)

    # 1. Deterministic results
    print("Checking deterministic results...")
    r1 = recommender.recommend(query_recipe_id="R00001", top_k=5, save_results=False)
    r2 = recommender.recommend(query_recipe_id="R00001", top_k=5, save_results=False)
    det_pass = (
        list(r1["recipe_id"]) == list(r2["recipe_id"])
        and np.allclose(r1["hybrid_score"], r2["hybrid_score"])
    )
    results["deterministic_results"] = det_pass
    print(f"  Deterministic results: {'PASS' if det_pass else 'FAIL'}")

    # 2. No duplicate recipes
    print("Checking no duplicate recipes...")
    no_dups = len(r1["recipe_id"]) == len(r1["recipe_id"].unique())
    results["no_duplicate_recipes"] = no_dups
    print(f"  No duplicate recipes: {'PASS' if no_dups else 'FAIL'}")

    # 3. Input recipe excluded
    print("Checking input recipe excluded...")
    excluded_pass = "R00001" not in r1["recipe_id"].values
    results["input_recipe_excluded"] = excluded_pass
    print(f"  Input recipe excluded: {'PASS' if excluded_pass else 'FAIL'}")

    # 4. Scores between 0 and 1
    print("Checking scores strictly in [0, 1]...")
    score_cols = ["hybrid_score", "similarity_score", "ingredient_match_score", "nutrition_score", "preference_score"]
    in_range = True
    for c in score_cols:
        vals = r1[c].values
        if not np.all((vals >= 0.0) & (vals <= 1.0)):
            in_range = False
            break
    results["scores_in_range_0_1"] = in_range
    print(f"  Scores in [0, 1]: {'PASS' if in_range else 'FAIL'}")

    # 5. Correct ranking order
    print("Checking ranking order monotonicity...")
    scores = r1["hybrid_score"].values
    monotonic = all(scores[i] >= scores[i + 1] - 1e-6 for i in range(len(scores) - 1))
    results["ranking_order_monotonic"] = monotonic
    print(f"  Ranking order monotonicity: {'PASS' if monotonic else 'FAIL'}")

    # 6. Hard filters respected (Vegetarian & Vegan)
    print("Checking hard dietary filters...")
    veg_recs = recommender.recommend(
        user_preferences=UserPreferences(vegetarian=True),
        top_k=20,
        save_results=False,
    )
    recipes_meta = recommender.preference_filter._recipes_metadata
    all_veg = all(recipes_meta[rid]["vegetarian"] for rid in veg_recs["recipe_id"])

    vegan_recs = recommender.recommend(
        user_preferences=UserPreferences(vegan=True),
        top_k=10,
        save_results=False,
    )
    all_vegan = all(
        recipes_meta[rid]["vegan"]
        or "vegan" in recipes_meta[rid]["diet_type"]
        or "vegan" in recipes_meta[rid]["recipe_name"].lower()
        for rid in vegan_recs["recipe_id"]
    )
    hard_filter_pass = all_veg and all_vegan
    results["hard_filters_respected"] = hard_filter_pass
    print(f"  Hard dietary filters: {'PASS' if hard_filter_pass else 'FAIL'}")

    # 7. Excluded ingredients respected
    print("Checking excluded ingredients...")
    exc_recs = recommender.recommend(
        available_ingredients=["rice", "onion", "tomato"],
        user_preferences=UserPreferences(excluded_ingredients=["chicken", "egg"]),
        top_k=20,
        save_results=False,
    )
    all_excluded_clean = True
    for rid in exc_recs["recipe_id"]:
        canons = recommender.ingredient_matcher._recipe_canonical_map.get(rid, set())
        all_ings = recommender.ingredient_matcher._recipe_all_ingredients.get(rid, [])
        if "chicken" in canons or "egg" in canons:
            all_excluded_clean = False
            break
        if any("chicken" in i or "egg" in i for i in all_ings):
            all_excluded_clean = False
            break
    results["excluded_ingredients_respected"] = all_excluded_clean
    print(f"  Excluded ingredients respected: {'PASS' if all_excluded_clean else 'FAIL'}")

    # 8. Required ingredients handled
    print("Checking required ingredients...")
    req_recs = recommender.recommend(
        user_preferences=UserPreferences(required_ingredients=["paneer"]),
        top_k=15,
        save_results=False,
    )
    all_have_req = all(
        "paneer" in recommender.ingredient_matcher._recipe_canonical_map.get(rid, set())
        for rid in req_recs["recipe_id"]
    )
    results["required_ingredients_handled"] = all_have_req
    print(f"  Required ingredients handled: {'PASS' if all_have_req else 'FAIL'}")

    # 9. Empty ingredient lists
    print("Checking empty ingredient lists...")
    empty_recs = recommender.recommend(
        available_ingredients=[],
        top_k=5,
        save_results=False,
    )
    empty_pass = len(empty_recs) == 5
    results["empty_ingredient_lists_handled"] = empty_pass
    print(f"  Empty ingredient lists handled: {'PASS' if empty_pass else 'FAIL'}")

    # 10. Unknown ingredients
    print("Checking unknown ingredients resilience...")
    unknown_recs = recommender.recommend(
        available_ingredients=["xyznonexistentfood123", "unknownspice999"],
        top_k=5,
        save_results=False,
    )
    unknown_pass = len(unknown_recs) == 5 and not unknown_recs["hybrid_score"].isna().any()
    results["unknown_ingredients_handled"] = unknown_pass
    print(f"  Unknown ingredients handled: {'PASS' if unknown_pass else 'FAIL'}")

    # 11. Unavailable nutrition handled safely
    print("Checking unavailable nutrition handling...")
    nut_goals = NutritionGoals(calorie_target=450.0, min_protein=15.0)
    nut_recs = recommender.recommend(
        nutrition_goals=nut_goals,
        top_k=10,
        save_results=False,
    )
    nut_pass = len(nut_recs) == 10 and not nut_recs["nutrition_score"].isna().any()
    results["unavailable_nutrition_handled"] = nut_pass
    print(f"  Unavailable nutrition handled: {'PASS' if nut_pass else 'FAIL'}")

    # 12. Top-k handling
    print("Checking top_k handling...")
    top3 = recommender.recommend(query_recipe_id="R00001", top_k=3, save_results=False)
    top7 = recommender.recommend(query_recipe_id="R00001", top_k=7, save_results=False)
    topk_pass = len(top3) == 3 and len(top7) == 7
    results["top_k_handling"] = topk_pass
    print(f"  Top-k handling: {'PASS' if topk_pass else 'FAIL'}")

    # 13. No division-by-zero
    print("Checking division-by-zero resilience...")
    # Zero targets, empty preferences, single ingredient edge cases
    div_zero_pass = True
    try:
        recommender.recommend(
            available_ingredients=["salt"],
            nutrition_goals=NutritionGoals(calorie_target=0.0, max_calories=0.0),
            user_preferences=UserPreferences(max_total_time_min=0.0),
            top_k=5,
            save_results=False,
        )
    except ZeroDivisionError:
        div_zero_pass = False
    results["no_division_by_zero"] = div_zero_pass
    print(f"  No division-by-zero: {'PASS' if div_zero_pass else 'FAIL'}")

    # 14. No NaN/inf scores
    print("Checking no NaN/inf scores...")
    no_nan_inf = True
    for df_chk in [r1, veg_recs, exc_recs, nut_recs]:
        for col in score_cols:
            if df_chk[col].isna().any() or np.isinf(df_chk[col].values).any():
                no_nan_inf = False
                break
    results["no_nan_or_inf_scores"] = no_nan_inf
    print(f"  No NaN or inf scores: {'PASS' if no_nan_inf else 'FAIL'}")

    # Save canonical recommendation results CSV
    recommender.recommend(
        query_recipe_id="R00001",
        top_k=10,
        save_results=True,
    )

    print("\n" + "=" * 60)
    all_passed = all(results.values())
    if all_passed:
        print("ALL RECOMMENDATION ENGINE VALIDATION CHECKS PASSED!")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"VALIDATION FAILED on: {failed}")
    print("=" * 60)

    return results


if __name__ == "__main__":
    res = validate_recommendation_engine()
    if not all(res.values()):
        sys.exit(1)
