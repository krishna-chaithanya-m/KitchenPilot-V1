"""Nutrition Outlier Validation Layer for KitchenPilot-V1.

Detects:
1. Extreme per-serving energy (> 5,000 kcal).
2. Extreme single-ingredient mass (> 10 kg for household recipes <= 10 servings).
3. Extreme single-ingredient liquid volume (> 10 L for household recipes <= 10 servings).

Reports:
recipe_id, recipe_name, metric, value, severity, cause, quality_status
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RECIPE_NUTRITION_PATH = PROJECT_ROOT / "data/processed/recipe_nutrition.csv"
INGREDIENT_NUTRITION_PATH = PROJECT_ROOT / "data/processed/recipe_ingredient_nutrition.csv"
QUALITY_CHECKED_PATH = PROJECT_ROOT / "data/processed/recipe_ingredients_quality_checked.csv"
OUTLIER_REPORT_PATH = PROJECT_ROOT / "data/mappings/nutrition_outliers_report.csv"


def validate_nutrition_outliers() -> pd.DataFrame:
    rec_df = pd.read_csv(RECIPE_NUTRITION_PATH)
    ing_df = pd.read_csv(INGREDIENT_NUTRITION_PATH)
    qc_df = pd.read_csv(QUALITY_CHECKED_PATH) if QUALITY_CHECKED_PATH.is_file() else None

    # Merge quality status from quality_checked if available
    if qc_df is not None:
        ing_merged = ing_df.merge(
            qc_df[["recipe_id", "original_ingredient", "quality_status"]].drop_duplicates(),
            on=["recipe_id", "original_ingredient"],
            how="left",
        )
    else:
        ing_merged = ing_df.copy()
        ing_merged["quality_status"] = "ORIGINAL"

    outlier_records: List[Dict[str, any]] = []

    # 1. Check per-serving calories > 5,000 kcal
    high_cal_recipes = rec_df[rec_df["per_serving_calories_kcal"] > 5000.0]
    for _, row in high_cal_recipes.iterrows():
        outlier_records.append({
            "recipe_id": row["recipe_id"],
            "recipe_name": row["recipe_name"],
            "metric": "per_serving_calories_kcal",
            "value": round(float(row["per_serving_calories_kcal"]), 2),
            "severity": "CRITICAL",
            "cause": "Extreme per-serving energy exceeds physiological plausibility (> 5,000 kcal/serv)",
            "quality_status": "FLAGGED_OUTLIER",
        })

    # 2. Merge servings to ingredient df for mass and volume checks
    rec_serv = dict(zip(rec_df["recipe_id"], rec_df["servings"]))
    rec_names = dict(zip(rec_df["recipe_id"], rec_df["recipe_name"]))

    for _, row in ing_merged.iterrows():
        rid = str(row["recipe_id"])
        rname = rec_names.get(rid, "")
        serv_raw = rec_serv.get(rid)
        try:
            servings = float(serv_raw) if pd.notna(serv_raw) else 1.0
            if servings <= 0:
                servings = 1.0
        except (ValueError, TypeError):
            servings = 1.0

        if servings <= 10.0:
            # Check ingredient mass > 10 kg (10,000 g)
            grams = float(row["grams"]) if pd.notna(row["grams"]) else None
            norm_unit = str(row["normalized_unit"]).lower() if pd.notna(row["normalized_unit"]) else ""
            parsed_qty = float(row["parsed_quantity"]) if pd.notna(row["parsed_quantity"]) else None
            q_status = str(row.get("quality_status", "ORIGINAL"))

            # Effective mass check
            if grams is not None and grams >= 10000.0:
                outlier_records.append({
                    "recipe_id": rid,
                    "recipe_name": rname,
                    "metric": "ingredient_mass_g",
                    "value": round(grams, 2),
                    "severity": "HIGH",
                    "cause": f"Single ingredient mass exceeds 10 kg ({grams/1000.0:.1f} kg) for {servings:.0f} servings",
                    "quality_status": q_status,
                })
            elif norm_unit in ("kg", "kilogram", "kilograms") and parsed_qty is not None and parsed_qty >= 10.0:
                outlier_records.append({
                    "recipe_id": rid,
                    "recipe_name": rname,
                    "metric": "ingredient_mass_kg",
                    "value": parsed_qty,
                    "severity": "HIGH",
                    "cause": f"Quantity specifies {parsed_qty} kg for {servings:.0f} servings",
                    "quality_status": q_status,
                })

            # Check liquid volume > 10 L
            if norm_unit in ("liter", "l", "liters", "litre", "litres") and parsed_qty is not None and parsed_qty >= 10.0:
                outlier_records.append({
                    "recipe_id": rid,
                    "recipe_name": rname,
                    "metric": "liquid_volume_l",
                    "value": parsed_qty,
                    "severity": "HIGH",
                    "cause": f"Liquid volume exceeds 10 L ({parsed_qty} L) for {servings:.0f} servings",
                    "quality_status": q_status,
                })

    outlier_df = pd.DataFrame(outlier_records)
    if not outlier_df.empty:
        outlier_df = outlier_df.drop_duplicates(subset=["recipe_id", "metric"])
    else:
        outlier_df = pd.DataFrame(columns=[
            "recipe_id", "recipe_name", "metric", "value", "severity", "cause", "quality_status"
        ])

    OUTLIER_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    outlier_df.to_csv(OUTLIER_REPORT_PATH, index=False)
    return outlier_df


def main() -> None:
    print("=" * 60)
    print("NUTRITION OUTLIER VALIDATION")
    print("=" * 60)

    outliers = validate_nutrition_outliers()
    high_cal_count = len(outliers[outliers["metric"] == "per_serving_calories_kcal"])
    mass_outlier_count = len(outliers[outliers["metric"].str.contains("mass", na=False)])
    volume_outlier_count = len(outliers[outliers["metric"].str.contains("volume", na=False)])

    print(f"Recipes with > 5,000 kcal/serving: {high_cal_count}")
    print(f"Household ingredients with > 10 kg mass (servings <= 10): {mass_outlier_count}")
    print(f"Household ingredients with > 10 L liquid volume (servings <= 10): {volume_outlier_count}")
    print(f"Total outlier flags: {len(outliers)}")
    print("\nDetailed Outlier Records:")
    if not outliers.empty:
        print(outliers.to_string(index=False))
    else:
        print("None detected.")

    print("\n" + "=" * 60)
    print("Outlier validation completed successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()
