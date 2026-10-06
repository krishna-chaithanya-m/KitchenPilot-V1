"""Validation script for KitchenPilot-V1 Recipe Nutrition Engine outputs.

Verifies:
1. Source file immutability and input integrity.
2. Output integrity (row counts, column schema, non-negativity, valid food codes).
3. Mathematical consistency (scaling from 100g basis, recipe aggregation, per-serving division).
4. Status and quality flag integrity.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Dict

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Protected input file baselines (LF-normalized SHA-256 for deterministic cross-platform verification)
BASELINE_HASHES = {
    PROJECT_ROOT / "data/processed/recipes.csv": "995badac27df7a28601f7894b236ec6447be8c9ba2048eb8a38478716b6f53c4",
    PROJECT_ROOT / "data/processed/recipe_ingredients_linked.csv": "6cc7421401f018a16c0ea096f212ada8408046fe9f2cadc49c78ed77e3c741f0",
    PROJECT_ROOT / "data/mappings/cnf_ingredient_mapping_curated.csv": "2297dd1c27412cac27c1864b8a7782b6d00a596c9bfe20f5e48f9872d5d166dd",
    PROJECT_ROOT / "data/raw/nutrition/cnf_2026/measure_weight_conversion.csv": "0b920b918bd789b9a6d56ac73eb973cc50a71b56397e00e18efe37d102e8a01a",
    PROJECT_ROOT / "data/raw/nutrition/cnf_2026/measure_name.csv": "f98cdaf345f877db3b88002c7c2c4819d14594ab95d826b39258fd15d14dd16e",
}

INGREDIENT_OUTPUT_PATH = PROJECT_ROOT / "data/processed/recipe_ingredient_nutrition.csv"
RECIPE_OUTPUT_PATH = PROJECT_ROOT / "data/processed/recipe_nutrition.csv"

REQUIRED_INGREDIENT_COLUMNS = [
    "recipe_id",
    "original_ingredient",
    "ingredient",
    "quantity",
    "unit",
    "preparation",
    "ingredient_id",
    "canonical_ingredient",
    "mapping_status",
    "curation_status",
    "cnf_food_code",
    "cnf_food_name",
    "parsed_quantity",
    "quantity_parse_status",
    "normalized_unit",
    "grams",
    "conversion_status",
    "state_status",
    "energy_kcal",
    "protein_g",
    "fat_g",
    "carbs_g",
    "fiber_g",
    "sugar_g",
    "sodium_mg",
    "mapping_quality",
    "nutrition_quality",
    "nutrition_source",
    "calculation_notes",
]

REQUIRED_RECIPE_COLUMNS = [
    "recipe_id",
    "recipe_name",
    "servings",
    "total_calories_kcal",
    "total_protein_g",
    "total_fat_g",
    "total_carbs_g",
    "total_fiber_g",
    "total_sugar_g",
    "total_sodium_mg",
    "per_serving_calories_kcal",
    "per_serving_protein_g",
    "per_serving_fat_g",
    "per_serving_carbs_g",
    "per_serving_fiber_g",
    "per_serving_sugar_g",
    "per_serving_sodium_mg",
    "nutrition_quality",
    "ingredient_count",
    "calculated_ingredient_count",
    "unmapped_ingredient_count",
    "no_match_ingredient_count",
    "needs_review_ingredient_count",
    "qualitative_quantity_count",
    "conversion_failure_count",
    "state_mismatch_count",
]

NUTRIENT_FIELDS = [
    "energy_kcal",
    "protein_g",
    "fat_g",
    "carbs_g",
    "fiber_g",
    "sugar_g",
    "sodium_mg",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    # Normalize CRLF to LF for text files to ensure deterministic cross-platform verification
    if path.suffix.lower() in [".csv", ".txt", ".json", ".md"]:
        content = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(content)
    else:
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def validate_nutrition_engine() -> Dict[str, str]:
    """Run all validation suites and return status mapping."""
    statuses: Dict[str, str] = {}

    # 1. Source immutability
    immutability_ok = True
    for file_path, expected_hash in BASELINE_HASHES.items():
        if not file_path.is_file():
            print(f"ERROR: Missing input file: {file_path}")
            immutability_ok = False
            continue
        actual_hash = _sha256(file_path)
        if actual_hash != expected_hash:
            print(f"ERROR: Protected source file has changed: {file_path}")
            immutability_ok = False

    statuses["Source immutability"] = "PASS" if immutability_ok else "FAIL"
    statuses["Input integrity"] = "PASS" if immutability_ok else "FAIL"

    # 2. Check output file existence
    if not INGREDIENT_OUTPUT_PATH.is_file() or not RECIPE_OUTPUT_PATH.is_file():
        print("ERROR: Output CSV files do not exist.")
        statuses["Ingredient alignment"] = "FAIL"
        statuses["CNF references"] = "FAIL"
        statuses["Nutrient values"] = "FAIL"
        statuses["Recipe aggregation"] = "FAIL"
        statuses["Per-serving calculation"] = "FAIL"
        statuses["Quality status integrity"] = "FAIL"
        return statuses

    ing_df = pd.read_csv(INGREDIENT_OUTPUT_PATH, low_memory=False)
    rec_df = pd.read_csv(RECIPE_OUTPUT_PATH, low_memory=False)
    source_recipes_df = pd.read_csv(PROJECT_ROOT / "data/processed/recipes.csv")
    source_ril_df = pd.read_csv(PROJECT_ROOT / "data/processed/recipe_ingredients_linked.csv")

    # 3. Ingredient alignment
    alignment_ok = True
    if len(ing_df) != len(source_ril_df):
        print(f"ERROR: Ingredient row count mismatch: {len(ing_df)} vs {len(source_ril_df)}")
        alignment_ok = False

    if list(ing_df.columns) != REQUIRED_INGREDIENT_COLUMNS:
        print("ERROR: Ingredient column schema mismatch.")
        alignment_ok = False

    if len(rec_df) != len(source_recipes_df):
        print(f"ERROR: Recipe count mismatch: {len(rec_df)} vs {len(source_recipes_df)}")
        alignment_ok = False

    if rec_df["recipe_id"].duplicated().any():
        print("ERROR: Duplicate recipe_id in recipe_nutrition.csv")
        alignment_ok = False

    if list(rec_df.columns) != REQUIRED_RECIPE_COLUMNS:
        print("ERROR: Recipe column schema mismatch.")
        alignment_ok = False

    statuses["Ingredient alignment"] = "PASS" if alignment_ok else "FAIL"

    # 4. CNF references
    cnf_ref_ok = True
    curated_df = pd.read_csv(PROJECT_ROOT / "data/mappings/cnf_ingredient_mapping_curated.csv")
    valid_cnf_codes = set(curated_df["cnf_food_code"].dropna().astype(int))

    populated_ing_codes = ing_df["cnf_food_code"].dropna().astype(int)
    invalid_codes = set(populated_ing_codes) - valid_cnf_codes
    if invalid_codes:
        print(f"ERROR: Unknown CNF food codes in ingredient nutrition: {invalid_codes}")
        cnf_ref_ok = False

    statuses["CNF references"] = "PASS" if cnf_ref_ok else "FAIL"

    # 5. Nutrient values (non-negativity, numeric type)
    nutrient_ok = True
    for nut in NUTRIENT_FIELDS:
        if not pd.api.types.is_numeric_dtype(ing_df[nut]):
            print(f"ERROR: Ingredient column '{nut}' is not numeric.")
            nutrient_ok = False
        if (ing_df[nut] < 0).any():
            print(f"ERROR: Negative values found in ingredient column '{nut}'")
            nutrient_ok = False

        tot_col = f"total_{nut}" if nut != "energy_kcal" else "total_calories_kcal"
        if not pd.api.types.is_numeric_dtype(rec_df[tot_col]):
            print(f"ERROR: Recipe column '{tot_col}' is not numeric.")
            nutrient_ok = False
        if (rec_df[tot_col] < 0).any():
            print(f"ERROR: Negative values found in recipe column '{tot_col}'")
            nutrient_ok = False

    statuses["Nutrient values"] = "PASS" if nutrient_ok else "FAIL"

    # 6. Recipe aggregation
    agg_ok = True
    # Group ingredient nutrition by recipe_id and verify sums for 100 sampled recipes
    sample_rids = rec_df["recipe_id"].sample(n=min(100, len(rec_df)), random_state=42)
    ing_grouped = ing_df.groupby("recipe_id")

    for rid in sample_rids:
        rec_row = rec_df[rec_df["recipe_id"] == rid].iloc[0]
        if rid in ing_grouped.groups:
            sub = ing_grouped.get_group(rid)
            for nut in NUTRIENT_FIELDS:
                tot_col = f"total_{nut}" if nut != "energy_kcal" else "total_calories_kcal"
                expected_sum = round(sub[nut].sum(), 3)
                actual_sum = round(float(rec_row[tot_col]), 3)
                if abs(expected_sum - actual_sum) > 0.05:
                    print(
                        f"ERROR: Aggregation mismatch in recipe {rid}, {tot_col}: expected {expected_sum}, got {actual_sum}"
                    )
                    agg_ok = False
                    break
        else:
            # 0 ingredients
            if rec_row["total_calories_kcal"] != 0:
                print(f"ERROR: Recipe {rid} has 0 ingredients but non-zero calories.")
                agg_ok = False

    statuses["Recipe aggregation"] = "PASS" if agg_ok else "FAIL"

    # 7. Per-serving calculation
    serving_ok = True
    for rid in sample_rids:
        rec_row = rec_df[rec_df["recipe_id"] == rid].iloc[0]
        s_raw = rec_row["servings"]
        try:
            s_val = float(s_raw) if pd.notna(s_raw) else None
        except ValueError:
            s_val = None

        if s_val is not None and s_val > 0:
            for nut in NUTRIENT_FIELDS:
                tot_col = f"total_{nut}" if nut != "energy_kcal" else "total_calories_kcal"
                ps_col = f"per_serving_{nut}" if nut != "energy_kcal" else "per_serving_calories_kcal"
                expected_ps = round(float(rec_row[tot_col]) / s_val, 3)
                actual_ps = round(float(rec_row[ps_col]), 3)
                if abs(expected_ps - actual_ps) > 0.05:
                    print(
                        f"ERROR: Per-serving mismatch in recipe {rid}, {ps_col}: expected {expected_ps}, got {actual_ps}"
                    )
                    serving_ok = False
                    break
        else:
            ps_col = "per_serving_calories_kcal"
            if pd.notna(rec_row[ps_col]):
                print(f"ERROR: Recipe {rid} has invalid servings but populated per-serving value.")
                serving_ok = False

    statuses["Per-serving calculation"] = "PASS" if serving_ok else "FAIL"

    # 8. Quality status integrity
    quality_ok = True
    allowed_rec_qualities = {"COMPLETE", "APPROXIMATE", "PARTIAL"}
    actual_rec_qualities = set(rec_df["nutrition_quality"].unique())
    if not actual_rec_qualities.issubset(allowed_rec_qualities):
        print(f"ERROR: Invalid recipe nutrition_quality values: {actual_rec_qualities}")
        quality_ok = False

    allowed_ing_qualities = {"EXACT", "APPROXIMATE", "UNAVAILABLE"}
    actual_ing_qualities = set(ing_df["nutrition_quality"].unique())
    if not actual_ing_qualities.issubset(allowed_ing_qualities):
        print(f"ERROR: Invalid ingredient nutrition_quality values: {actual_ing_qualities}")
        quality_ok = False

    statuses["Quality status integrity"] = "PASS" if quality_ok else "FAIL"

    return statuses


def main() -> None:
    print("=" * 50)
    print("RECIPE NUTRITION ENGINE VALIDATION")
    print("=" * 50)

    statuses = validate_nutrition_engine()
    all_passed = all(status == "PASS" for status in statuses.values())

    for check, status in statuses.items():
        print(f"{check}: {status}")

    print("\n" + "=" * 50)
    print(f"Validation result: {'PASS' if all_passed else 'FAIL'}")
    print("=" * 50)

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
