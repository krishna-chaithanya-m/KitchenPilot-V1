"""Regression and Quality Tests for KitchenPilot-V1 Nutrition Improvements.

Verifies:
1. No negative nutrients in recipe or ingredient outputs.
2. Recipe IDs remain unchanged and unique.
3. Recipe count remains exactly 6,871.
4. Ingredient rows remain strictly aligned with recipe_ingredients_linked.csv (84,246 rows).
5. Protected source files are immutable and unmutated.
6. Whole-item counts use explicit item-mass calibration (30 almonds, 1 almond, 8 cashews, 6 garlic cloves, 3 tomatoes, 1 onion).
7. Cooked-state handling works (cooked rice, boiled moong dal, boiled chickpeas, boiled potato, cooked peas).
8. Qualitative estimates are explicitly marked ESTIMATED / APPROXIMATE.
9. No unsupported automatic NO_MATCH mappings.
10. Unit sanity anomalies (e.g. 750 Kg chicken, 200 liter coconut milk) are correctly flagged.
11. Recipe aggregation sums remain deterministic and strictly conserved.
12. Per-serving calculations remain mathematically correct.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.nutrition.measure_converter import MeasureConverter
from src.nutrition.recipe_nutrition_engine import RecipeNutritionEngine
from src.validation.unit_sanity_validator import UnitSanityValidator

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Protected source baseline hashes (LF-normalized SHA-256 for deterministic cross-platform verification)
BASELINE_HASHES = {
    PROJECT_ROOT / "data/processed/recipes.csv": "995badac27df7a28601f7894b236ec6447be8c9ba2048eb8a38478716b6f53c4",
    PROJECT_ROOT / "data/processed/recipe_ingredients_linked.csv": "6cc7421401f018a16c0ea096f212ada8408046fe9f2cadc49c78ed77e3c741f0",
    PROJECT_ROOT / "data/mappings/cnf_ingredient_mapping_curated.csv": "2297dd1c27412cac27c1864b8a7782b6d00a596c9bfe20f5e48f9872d5d166dd",
    PROJECT_ROOT / "data/raw/nutrition/cnf_2026/measure_weight_conversion.csv": "0b920b918bd789b9a6d56ac73eb973cc50a71b56397e00e18efe37d102e8a01a",
    PROJECT_ROOT / "data/raw/nutrition/cnf_2026/measure_name.csv": "f98cdaf345f877db3b88002c7c2c4819d14594ab95d826b39258fd15d14dd16e",
}

NUTRIENT_COLS = [
    "energy_kcal",
    "protein_g",
    "fat_g",
    "carbs_g",
    "fiber_g",
    "sugar_g",
    "sodium_mg",
]


@pytest.fixture(scope="module")
def converter():
    return MeasureConverter()


@pytest.fixture(scope="module")
def engine():
    return RecipeNutritionEngine(enable_state_yield=True, enable_qualitative_estimates=True)


@pytest.fixture(scope="module")
def ingredient_df():
    return pd.read_csv(PROJECT_ROOT / "data/processed/recipe_ingredient_nutrition.csv", low_memory=False)


@pytest.fixture(scope="module")
def recipe_df():
    return pd.read_csv(PROJECT_ROOT / "data/processed/recipe_nutrition.csv", low_memory=False)


# ---------------------------------------------------------------------------
# Test 1: No negative nutrients
# ---------------------------------------------------------------------------
def test_no_negative_nutrients(ingredient_df, recipe_df):
    for nut in NUTRIENT_COLS:
        assert (ingredient_df[nut] >= 0).all(), f"Found negative values in ingredient column {nut}"
        tot_col = f"total_{nut}" if nut != "energy_kcal" else "total_calories_kcal"
        ps_col = f"per_serving_{nut}" if nut != "energy_kcal" else "per_serving_calories_kcal"
        assert (recipe_df[tot_col] >= 0).all(), f"Found negative values in recipe column {tot_col}"
        valid_ps = recipe_df[ps_col].dropna()
        assert (valid_ps >= 0).all(), f"Found negative values in recipe column {ps_col}"


# ---------------------------------------------------------------------------
# Test 2: Recipe IDs unchanged and unique
# ---------------------------------------------------------------------------
def test_recipe_ids_unchanged(recipe_df):
    source_recipes = pd.read_csv(PROJECT_ROOT / "data/processed/recipes.csv")
    assert list(recipe_df["recipe_id"]) == list(source_recipes["recipe_id"])
    assert recipe_df["recipe_id"].nunique() == len(recipe_df)


# ---------------------------------------------------------------------------
# Test 3: Recipe count remains 6,871
# ---------------------------------------------------------------------------
def test_recipe_count(recipe_df):
    assert len(recipe_df) == 6871


# ---------------------------------------------------------------------------
# Test 4: Ingredient rows remain aligned (84,246)
# ---------------------------------------------------------------------------
def test_ingredient_rows_aligned(ingredient_df):
    source_ril = pd.read_csv(PROJECT_ROOT / "data/processed/recipe_ingredients_linked.csv")
    assert len(ingredient_df) == len(source_ril) == 84246
    assert list(ingredient_df["recipe_id"]) == list(source_ril["recipe_id"])


# ---------------------------------------------------------------------------
# Test 5: No accidental source-data mutation
# ---------------------------------------------------------------------------
def test_source_immutability():
    for fpath, expected_hash in BASELINE_HASHES.items():
        assert fpath.is_file(), f"Missing baseline file: {fpath}"
        content = fpath.read_bytes().replace(b"\r\n", b"\n")
        actual_hash = hashlib.sha256(content).hexdigest()
        assert actual_hash == expected_hash, f"Protected file {fpath.name} was accidentally mutated!"


# ---------------------------------------------------------------------------
# Test 6: Whole-item counts use item-mass calibration
# ---------------------------------------------------------------------------
def test_whole_item_mass_calibration(converter):
    # 30 almonds: 30 * 1.2g = 36.0g (NOT ~1800g from volumetric whole container measure)
    res_30_almonds = converter.convert(
        food_code=2534,
        quantity=30.0,
        normalized_unit=None,
        canonical_ingredient="almond",
    )
    assert res_30_almonds.conversion_status == "CNF_MEASURE"
    assert res_30_almonds.grams == 36.0
    assert "Culinary item mass calibration" in res_30_almonds.notes

    # 1 almond: 1.2g
    res_1_almond = converter.convert(
        food_code=2534,
        quantity=1.0,
        normalized_unit=None,
        canonical_ingredient="almond",
    )
    assert res_1_almond.grams == 1.2

    # 8 cashews: 8 * 1.5g = 12.0g
    res_8_cashews = converter.convert(
        food_code=2548,
        quantity=8.0,
        normalized_unit=None,
        canonical_ingredient="cashew",
    )
    assert res_8_cashews.grams == 12.0

    # 6 garlic cloves: 6 * 3.0g = 18.0g
    res_6_garlic = converter.convert(
        food_code=2394,
        quantity=6.0,
        normalized_unit="clove",
        canonical_ingredient="garlic",
    )
    assert res_6_garlic.grams == 18.0

    # 3 tomatoes: 3 * 123.0g = 369.0g
    res_3_tomatoes = converter.convert(
        food_code=2460,
        quantity=3.0,
        normalized_unit=None,
        canonical_ingredient="tomato",
    )
    assert res_3_tomatoes.grams == 369.0

    # 1 onion: 110.0g
    res_1_onion = converter.convert(
        food_code=2401,
        quantity=1.0,
        normalized_unit=None,
        canonical_ingredient="onion",
    )
    assert res_1_onion.grams == 110.0


# ---------------------------------------------------------------------------
# Test 7: Cooked-state handling works
# ---------------------------------------------------------------------------
def test_cooked_state_handling(engine):
    # 1 cup cooked rice (yield factor 0.38): ~195.5g * 0.38 = ~74.3g raw rice
    dummy_rice = {
        "recipe_id": "TEST_RICE",
        "original_ingredient": "1 cup rice - cooked",
        "ingredient": "rice",
        "quantity": "1",
        "unit": "cup",
        "preparation": "cooked",
        "ingredient_id": "ING00099",
        "canonical_ingredient": "rice",
        "mapping_status": "MAPPED_CANONICAL",
    }
    p_rice = engine._process_ingredient_row(dummy_rice)
    assert p_rice["conversion_status"] == "COOKING_YIELD_CONVERSION"
    assert p_rice["energy_kcal"] > 0
    assert p_rice["nutrition_quality"] == "APPROXIMATE"
    assert p_rice["nutrition_source"] == "CNF_2026_YIELD"

    # Boiled moong dal (yield factor 0.385)
    dummy_moong = {
        "recipe_id": "TEST_MOONG",
        "original_ingredient": "1 cup moong dal - boiled",
        "ingredient": "moong dal",
        "quantity": "1",
        "unit": "cup",
        "preparation": "boiled",
        "ingredient_id": "ING00075",
        "canonical_ingredient": "moong dal",
        "mapping_status": "MAPPED_CANONICAL",
    }
    p_moong = engine._process_ingredient_row(dummy_moong)
    assert p_moong["conversion_status"] == "COOKING_YIELD_CONVERSION"
    assert p_moong["energy_kcal"] > 0

    # Boiled potato (yield factor 1.0)
    dummy_potato = {
        "recipe_id": "TEST_POTATO",
        "original_ingredient": "2 potatoes - boiled",
        "ingredient": "potato",
        "quantity": "2",
        "unit": None,
        "preparation": "boiled",
        "ingredient_id": "ING00092",
        "canonical_ingredient": "potato",
        "mapping_status": "MAPPED_CANONICAL",
    }
    p_potato = engine._process_ingredient_row(dummy_potato)
    assert p_potato["conversion_status"] == "COOKING_YIELD_CONVERSION"
    assert p_potato["energy_kcal"] > 0

    # Cooked green peas (yield factor 1.0)
    dummy_peas = {
        "recipe_id": "TEST_PEAS",
        "original_ingredient": "1 cup green peas - cooked",
        "ingredient": "green peas",
        "quantity": "1",
        "unit": "cup",
        "preparation": "cooked",
        "ingredient_id": "ING00066",
        "canonical_ingredient": "green peas",
        "mapping_status": "MAPPED_CANONICAL",
    }
    p_peas = engine._process_ingredient_row(dummy_peas)
    assert p_peas["conversion_status"] == "COOKING_YIELD_CONVERSION"
    assert p_peas["energy_kcal"] > 0


# ---------------------------------------------------------------------------
# Test 8: Qualitative estimates are explicitly marked ESTIMATED
# ---------------------------------------------------------------------------
def test_qualitative_estimates_marked_estimated(engine):
    dummy_oil = {
        "recipe_id": "TEST_OIL",
        "original_ingredient": "Sunflower Oil - as required",
        "ingredient": "Sunflower Oil",
        "quantity": None,
        "unit": None,
        "preparation": "as required",
        "ingredient_id": "ING00113",
        "canonical_ingredient": "sunflower oil",
        "mapping_status": "MAPPED_CANONICAL",
    }
    p_oil = engine._process_ingredient_row(dummy_oil)
    assert p_oil["conversion_status"] == "ESTIMATED_QUALITATIVE"
    assert p_oil["nutrition_quality"] == "APPROXIMATE"
    assert p_oil["nutrition_source"] == "ESTIMATED_QUALITATIVE"
    assert p_oil["energy_kcal"] > 100.0  # 1 tbsp ~ 122 kcal
    assert "ESTIMATED" in p_oil["calculation_notes"]

    # Salt remains ZERO_CALORIE_QUALITATIVE and EXACT
    dummy_salt = {
        "recipe_id": "TEST_SALT",
        "original_ingredient": "Salt - to taste",
        "ingredient": "Salt",
        "quantity": None,
        "unit": None,
        "preparation": "to taste",
        "ingredient_id": "ING00103",
        "canonical_ingredient": "salt",
        "mapping_status": "MAPPED_CANONICAL",
    }
    p_salt = engine._process_ingredient_row(dummy_salt)
    assert p_salt["conversion_status"] == "ZERO_CALORIE_QUALITATIVE"
    assert p_salt["nutrition_quality"] == "EXACT"
    assert p_salt["energy_kcal"] == 0.0


# ---------------------------------------------------------------------------
# Test 9: No unsupported automatic NO_MATCH mappings
# ---------------------------------------------------------------------------
def test_no_unsupported_no_match_mappings(engine):
    # urad dal (ING00122) is NO_MATCH in curated mapping
    dummy_urad = {
        "recipe_id": "TEST_URAD",
        "original_ingredient": "1 cup white urad dal",
        "ingredient": "white urad dal",
        "quantity": "1",
        "unit": "cup",
        "preparation": None,
        "ingredient_id": "ING00122",
        "canonical_ingredient": "urad dal",
        "mapping_status": "MAPPED_CANONICAL",
    }
    p_urad = engine._process_ingredient_row(dummy_urad)
    assert p_urad["curation_status"] == "NO_MATCH"
    assert p_urad["conversion_status"] == "NO_MATCH"
    assert p_urad["nutrition_quality"] == "UNAVAILABLE"
    assert p_urad["energy_kcal"] == 0.0


# ---------------------------------------------------------------------------
# Test 10: Unit sanity anomalies are flagged
# ---------------------------------------------------------------------------
def test_unit_sanity_anomalies_flagged():
    validator = UnitSanityValidator()
    review_df = validator.validate()
    critical_rids = set(review_df[review_df["severity"] == "CRITICAL"]["recipe_id"])
    assert "R05587" in critical_rids  # 750 Kg Chicken
    assert "R07106" in critical_rids  # 200 liter Coconut milk
    assert "R10172" in critical_rids  # 250 kg Watermelon


# ---------------------------------------------------------------------------
# Test 11: Recipe aggregation remains deterministic
# ---------------------------------------------------------------------------
def test_recipe_aggregation_deterministic(ingredient_df, recipe_df):
    sample_rids = recipe_df["recipe_id"].sample(n=50, random_state=42)
    ing_grouped = ingredient_df.groupby("recipe_id")

    for rid in sample_rids:
        rec_row = recipe_df[recipe_df["recipe_id"] == rid].iloc[0]
        if rid in ing_grouped.groups:
            sub = ing_grouped.get_group(rid)
            for nut in NUTRIENT_COLS:
                tot_col = f"total_{nut}" if nut != "energy_kcal" else "total_calories_kcal"
                expected = round(sub[nut].sum(), 3)
                actual = round(float(rec_row[tot_col]), 3)
                assert abs(expected - actual) <= 0.05, f"Aggregation mismatch in {rid} for {tot_col}"


# ---------------------------------------------------------------------------
# Test 12: Per-serving calculations remain correct
# ---------------------------------------------------------------------------
def test_per_serving_calculations(recipe_df):
    sample_rids = recipe_df["recipe_id"].sample(n=50, random_state=42)
    for rid in sample_rids:
        rec_row = recipe_df[recipe_df["recipe_id"] == rid].iloc[0]
        try:
            serv = float(rec_row["servings"])
        except (ValueError, TypeError):
            serv = None

        if serv is not None and serv > 0:
            for nut in NUTRIENT_COLS:
                tot_col = f"total_{nut}" if nut != "energy_kcal" else "total_calories_kcal"
                ps_col = f"per_serving_{nut}" if nut != "energy_kcal" else "per_serving_calories_kcal"
                expected_ps = round(float(rec_row[tot_col]) / serv, 3)
                actual_ps = round(float(rec_row[ps_col]), 3)
                assert abs(expected_ps - actual_ps) <= 0.05, f"Per-serving mismatch in {rid} for {ps_col}"


# ---------------------------------------------------------------------------
# Test 13: High-confidence unit prefix corrections preserved separately
# ---------------------------------------------------------------------------
def test_unit_prefix_corrections(ingredient_df):
    # R05587: 750 Kg Chicken -> effective = 750 g
    r_5587 = ingredient_df[ingredient_df["recipe_id"] == "R05587"]
    chicken = r_5587[r_5587["original_ingredient"].str.contains("750", na=False)].iloc[0]
    assert "750" in str(chicken["quantity"])
    assert "kg" in str(chicken["unit"]).lower()
    assert chicken["parsed_quantity"] == 750.0
    assert chicken["normalized_unit"] == "g"
    assert chicken["grams"] == 750.0
    assert chicken["conversion_status"] == "SOURCE_UNIT_CORRECTION"
    assert chicken["nutrition_source"] == "QUALITY_CORRECTED"
    assert "SOURCE_UNIT_CORRECTION" in chicken["calculation_notes"]

    # R07106: 200 liter Coconut milk -> effective = 200 ml
    r_7106 = ingredient_df[ingredient_df["recipe_id"] == "R07106"]
    cmilk = r_7106[r_7106["original_ingredient"].str.contains("200", na=False)].iloc[0]
    assert "200" in str(cmilk["quantity"])
    assert "liter" in str(cmilk["unit"]).lower()
    assert cmilk["parsed_quantity"] == 200.0
    assert cmilk["normalized_unit"] == "ml"
    assert cmilk["grams"] < 250.0
    assert cmilk["conversion_status"] == "SOURCE_UNIT_CORRECTION"
    assert cmilk["nutrition_source"] == "QUALITY_CORRECTED"

    # R10172: 250 kg Watermelon -> effective = 250 g
    r_10172 = ingredient_df[ingredient_df["recipe_id"] == "R10172"]
    wmelon = r_10172[r_10172["original_ingredient"].str.contains("250", na=False)].iloc[0]
    assert "250" in str(wmelon["quantity"])
    assert "kg" in str(wmelon["unit"]).lower()
    assert wmelon["parsed_quantity"] == 250.0
    assert wmelon["normalized_unit"] == "g"
    assert wmelon["conversion_status"] == "SOURCE_UNIT_CORRECTION"


# ---------------------------------------------------------------------------
# Test 14: Corrected effective quantities applied to nutrition calculations
# ---------------------------------------------------------------------------
def test_corrected_nutrition_applied(ingredient_df, recipe_df):
    # R05587: Chicken mass is 750g, not 750,000g; per-serving calories < 1,000 kcal
    r5587_rec = recipe_df[recipe_df["recipe_id"] == "R05587"].iloc[0]
    assert r5587_rec["per_serving_calories_kcal"] < 1000.0
    r5587_ing = ingredient_df[ingredient_df["recipe_id"] == "R05587"]
    chicken_row = r5587_ing[r5587_ing["original_ingredient"].str.contains("750", na=False)].iloc[0]
    assert chicken_row["grams"] == 750.0
    assert chicken_row["conversion_status"] == "SOURCE_UNIT_CORRECTION"
    assert chicken_row["nutrition_source"] == "QUALITY_CORRECTED"
    assert "SOURCE_UNIT_CORRECTION" in chicken_row["calculation_notes"]

    # R07106: Coconut milk mass ~191g, not 191,040g; per-serving calories < 1,000 kcal
    r7106_rec = recipe_df[recipe_df["recipe_id"] == "R07106"].iloc[0]
    assert r7106_rec["per_serving_calories_kcal"] < 1000.0
    r7106_ing = ingredient_df[ingredient_df["recipe_id"] == "R07106"]
    cmilk_row = r7106_ing[r7106_ing["original_ingredient"].str.contains("200", na=False)].iloc[0]
    assert cmilk_row["grams"] < 250.0
    assert cmilk_row["conversion_status"] == "SOURCE_UNIT_CORRECTION"
    assert cmilk_row["nutrition_source"] == "QUALITY_CORRECTED"


# ---------------------------------------------------------------------------
# Test 15: Soaked vs cooked state provenance handling
# ---------------------------------------------------------------------------
def test_soaked_vs_cooked_state_provenance(engine):
    # R00006: soaked rice -> SOAKING_YIELD_ESTIMATE
    dummy_soaked_rice = {
        "recipe_id": "R00006",
        "original_ingredient": "1 cup rice - soaked for 20 minutes",
        "ingredient": "rice",
        "quantity": "1",
        "unit": "cup",
        "preparation": "soaked for 20 minutes",
        "ingredient_id": "ING00099",
        "canonical_ingredient": "rice",
        "mapping_status": "MAPPED_CANONICAL",
    }
    p_s_rice = engine._process_ingredient_row(dummy_soaked_rice)
    assert p_s_rice["state_status"] == "SOAKING_YIELD_ESTIMATE"
    assert p_s_rice["conversion_status"] == "SOAKING_YIELD_ESTIMATE"
    assert p_s_rice["nutrition_source"] == "SOAKING_YIELD_ESTIMATE"
    assert "SOAKING_YIELD_ESTIMATE" in p_s_rice["calculation_notes"]

    # R00006: soaked moong dal -> SOAKING_YIELD_ESTIMATE
    dummy_soaked_moong = {
        "recipe_id": "R00006",
        "original_ingredient": "1/2 cup yellow moong dal - soaked for 20 minutes",
        "ingredient": "yellow moong dal",
        "quantity": "1/2",
        "unit": "cup",
        "preparation": "soaked for 20 minutes",
        "ingredient_id": "ING00075",
        "canonical_ingredient": "moong dal",
        "mapping_status": "MAPPED_CANONICAL",
    }
    p_s_moong = engine._process_ingredient_row(dummy_soaked_moong)
    assert p_s_moong["state_status"] == "SOAKING_YIELD_ESTIMATE"
    assert p_s_moong["conversion_status"] == "SOAKING_YIELD_ESTIMATE"
    assert p_s_moong["nutrition_source"] == "SOAKING_YIELD_ESTIMATE"

    # Soaked tamarind without established factor -> STATE_REVIEW_REQUIRED
    dummy_soaked_tamarind = {
        "recipe_id": "TEST_TAMARIND",
        "original_ingredient": "lemon sized tamarind - soaked in water",
        "ingredient": "tamarind",
        "quantity": "1",
        "unit": None,
        "preparation": "soaked in water",
        "ingredient_id": "ING00115",
        "canonical_ingredient": "tamarind",
        "mapping_status": "MAPPED_CANONICAL",
    }
    p_s_tam = engine._process_ingredient_row(dummy_soaked_tamarind)
    assert p_s_tam["state_status"] == "STATE_REVIEW_REQUIRED"
    assert p_s_tam["conversion_status"] == "STATE_REVIEW_REQUIRED"
    assert p_s_tam["nutrition_quality"] == "UNAVAILABLE"
    assert "STATE_REVIEW_REQUIRED" in p_s_tam["calculation_notes"]


# ---------------------------------------------------------------------------
# Test 16: Outlier validation reports zero > 5,000 kcal/serving recipes
# ---------------------------------------------------------------------------
def test_outlier_validation(recipe_df):
    from src.validation.validate_nutrition_outliers import validate_nutrition_outliers
    outliers = validate_nutrition_outliers()
    high_cal = outliers[outliers["metric"] == "per_serving_calories_kcal"]
    assert len(high_cal) == 0, f"Found unexpected recipes with > 5,000 kcal/serving: {high_cal['recipe_id'].tolist()}"


# ---------------------------------------------------------------------------
# Test 17: Black peppercorn safety test (Must NOT produce 176.505g)
# ---------------------------------------------------------------------------
def test_peppercorn_safety(converter, ingredient_df):
    # Test converter directly
    res = converter.convert(
        food_code=198,
        quantity=3.0,
        normalized_unit=None,
        original_ingredient="3 Whole Black Peppercorns",
        canonical_ingredient="black pepper",
    )
    assert res.grams != 176.505, "Regression: 3 peppercorns produced 176.505g!"
    assert res.grams == 0.15, f"Expected 0.15g (0.05g/peppercorn), got {res.grams}"

    # Verify R05587 row in generated dataset
    r5587_rows = ingredient_df[ingredient_df["recipe_id"] == "R05587"]
    pep_row = r5587_rows[r5587_rows["original_ingredient"].str.contains("Peppercorn", case=False, na=False)].iloc[0]
    assert pep_row["grams"] != 176.505
    assert pep_row["grams"] == 0.15
    assert "0.05g/peppercorn" in pep_row["calculation_notes"]

    # Verify unitless black pepper powder does NOT use 100 ml whole (58.835g)
    powder_res = converter.convert(
        food_code=198,
        quantity=4.0,
        normalized_unit=None,
        original_ingredient="4 Black pepper powder",
        canonical_ingredient="black pepper",
    )
    assert powder_res.grams is None
    assert powder_res.conversion_status == "NO_CNF_CONVERSION"


# ---------------------------------------------------------------------------
# Test 18: Twelve explicit regression cases from hardening pass
# ---------------------------------------------------------------------------
def test_twelve_regression_cases(converter, ingredient_df, recipe_df):
    # 1. 3 black peppercorns
    r1 = converter.convert(198, 3.0, None, "3 Whole Black Peppercorns", canonical_ingredient="black pepper")
    assert r1.grams != 176.505
    assert r1.grams == 0.15

    # 2. 30 almonds
    r2 = converter.convert(2534, 30.0, None, "30 almonds", canonical_ingredient="almond")
    assert r2.grams == 36.0

    # 3. 30 cashews
    r3 = converter.convert(2548, 30.0, None, "30 cashews", canonical_ingredient="cashew")
    assert r3.grams == 45.0

    # 4. 3 tomatoes
    r4 = converter.convert(2460, 3.0, None, "3 tomatoes", canonical_ingredient="tomato")
    assert r4.grams == 369.0

    # 5. 1 green chilli
    r5 = converter.convert(2322, 1.0, None, "1 green chilli", canonical_ingredient="green chilli")
    assert r5.grams == 45.0
    assert r5.conversion_status == "CNF_MEASURE"

    # 6. 2 tbsp ghee
    r6 = converter.convert(7829, 2.0, "tbsp", "2 tablespoons Ghee", canonical_ingredient="ghee")
    assert r6.grams == 25.6
    assert r6.conversion_status == "CNF_MEASURE"

    # 7. 1 inch ginger
    r7 = converter.convert(2395, 1.0, "inch", "1 inch Ginger", canonical_ingredient="ginger")
    assert r7.grams == 5.0
    assert r7.conversion_status == "CNF_MEASURE"

    # 8. 1 inch cinnamon
    r8 = converter.convert(195, 1.0, "inch", "1 inch Cinnamon Stick", canonical_ingredient="cinnamon")
    assert r8.grams == 1.3
    assert r8.conversion_status == "CNF_MEASURE"

    # 9. 750 kg chicken source correction (R05587)
    r5587_rec = recipe_df[recipe_df["recipe_id"] == "R05587"].iloc[0]
    assert r5587_rec["per_serving_calories_kcal"] < 1000.0
    r5587_ing = ingredient_df[ingredient_df["recipe_id"] == "R05587"]
    chicken = r5587_ing[r5587_ing["original_ingredient"].str.contains("750", na=False)].iloc[0]
    assert chicken["grams"] == 750.0

    # 10. 200 L coconut milk source correction (R07106)
    r7106_rec = recipe_df[recipe_df["recipe_id"] == "R07106"].iloc[0]
    assert r7106_rec["per_serving_calories_kcal"] < 1000.0
    r7106_ing = ingredient_df[ingredient_df["recipe_id"] == "R07106"]
    cmilk = r7106_ing[r7106_ing["original_ingredient"].str.contains("200", na=False)].iloc[0]
    assert cmilk["grams"] < 250.0

    # 11. 250 kg watermelon source correction (R10172)
    r10172_ing = ingredient_df[ingredient_df["recipe_id"] == "R10172"]
    wmelon = r10172_ing[r10172_ing["original_ingredient"].str.contains("250", na=False)].iloc[0]
    assert pd.isna(wmelon["grams"]) or wmelon["grams"] == 0.0
    assert wmelon["nutrition_quality"] == "UNAVAILABLE"
    assert "QUALITY_CORRECTED" in wmelon["calculation_notes"]

    # 12. Arbitrary count must never use generic 100 ml whole/packed/container conversion
    # 10 raisins without unit must NOT use 100 ml packed (64.0g)
    raisin_res = converter.convert(1745, 10.0, None, "10 raisins", canonical_ingredient="raisin")
    assert raisin_res.grams is None
    assert raisin_res.conversion_status == "NO_CNF_CONVERSION"

    # 1 dry red chilli without unit must NOT use 100 ml whole/packed
    chilli_res = converter.convert(2355, 1.0, None, "1 dry red chilli", canonical_ingredient="dry red chilli")
    assert chilli_res.grams is None
    assert chilli_res.conversion_status == "NO_CNF_CONVERSION"

    # Global check in generated dataset: zero count items using 100 ml whole/packed/container
    count_rows = ingredient_df[ingredient_df["unit"].isna() | (ingredient_df["unit"] == "piece")]
    unsafe_matches = count_rows["calculation_notes"].str.contains(
        r"100\s*ml\s*(?:whole|packed|container)",
        case=False,
        na=False,
    )
    assert unsafe_matches.sum() == 0, f"Found {unsafe_matches.sum()} unsafe discrete conversions in generated dataset!"

    # Verify raw source values remain unchanged
    source_ril = pd.read_csv(PROJECT_ROOT / "data/processed/recipe_ingredients_linked.csv")
    raw_5587 = source_ril[source_ril["recipe_id"] == "R05587"]
    assert "750 Kg Chicken" in raw_5587["original_ingredient"].values
    raw_7106 = source_ril[source_ril["recipe_id"] == "R07106"]
    assert any("200 liter" in str(x) for x in raw_7106["original_ingredient"].values)
    raw_10172 = source_ril[source_ril["recipe_id"] == "R10172"]
    assert any("250 kg" in str(x) for x in raw_10172["original_ingredient"].values)


