"""Unit tests for the KitchenPilot-V1 Recipe Nutrition Engine."""

import pytest
from src.nutrition.quantity_parser import (
    parse_quantity,
    normalize_unit,
    QuantityParseResult,
)
from src.nutrition.measure_converter import MeasureConverter, ConversionResult
from src.nutrition.nutrient_lookup import NutrientLookup, NutrientProfile
from src.nutrition.recipe_nutrition_engine import RecipeNutritionEngine


# ---------------------------------------------------------------------------
# 1. Quantity Parser Tests
# ---------------------------------------------------------------------------
def test_integer_quantities():
    """Test integer quantities parsing."""
    res1 = parse_quantity("1")
    assert res1.parse_status == "PARSED_NUMERIC"
    assert res1.parsed_quantity == 1.0

    res2 = parse_quantity("10")
    assert res2.parse_status == "PARSED_NUMERIC"
    assert res2.parsed_quantity == 10.0

    res3 = parse_quantity(5)
    assert res3.parse_status == "PARSED_NUMERIC"
    assert res3.parsed_quantity == 5.0


def test_simple_fractions():
    """Test simple fraction parsing."""
    res1 = parse_quantity("1/2")
    assert res1.parse_status == "PARSED_FRACTION"
    assert res1.parsed_quantity == 0.5

    res2 = parse_quantity("1/4")
    assert res2.parse_status == "PARSED_FRACTION"
    assert res2.parsed_quantity == 0.25

    res3 = parse_quantity("3/4")
    assert res3.parse_status == "PARSED_FRACTION"
    assert res3.parsed_quantity == 0.75

    res4 = parse_quantity("1/8")
    assert res4.parse_status == "PARSED_FRACTION"
    assert res4.parsed_quantity == 0.125


def test_mixed_fractions():
    """Test mixed fraction parsing."""
    res1 = parse_quantity("1 1/2")
    assert res1.parse_status == "PARSED_MIXED_FRACTION"
    assert res1.parsed_quantity == 1.5

    res2 = parse_quantity("2 1/2")
    assert res2.parse_status == "PARSED_MIXED_FRACTION"
    assert res2.parsed_quantity == 2.5

    res3 = parse_quantity("1 1/4")
    assert res3.parse_status == "PARSED_MIXED_FRACTION"
    assert res3.parsed_quantity == 1.25

    res4 = parse_quantity("3 1/2")
    assert res4.parse_status == "PARSED_MIXED_FRACTION"
    assert res4.parsed_quantity == 3.5

    res5 = parse_quantity("1-1/2")
    assert res5.parse_status == "PARSED_MIXED_FRACTION"
    assert res5.parsed_quantity == 1.5


def test_known_unspaced_fractions():
    """Test known unspaced fraction anomaly normalization."""
    res1 = parse_quantity("11/2")
    assert res1.parse_status == "PARSED_ANOMALY"
    assert res1.parsed_quantity == 1.5

    res2 = parse_quantity("21/2")
    assert res2.parse_status == "PARSED_ANOMALY"
    assert res2.parsed_quantity == 2.5

    res3 = parse_quantity("11/4")
    assert res3.parse_status == "PARSED_ANOMALY"
    assert res3.parsed_quantity == 1.25


def test_missing_quantity():
    """Test missing or blank quantity handling."""
    res1 = parse_quantity(None)
    assert res1.parse_status == "MISSING_QUANTITY"
    assert res1.parsed_quantity is None

    res2 = parse_quantity("")
    assert res2.parse_status == "MISSING_QUANTITY"
    assert res2.parsed_quantity is None

    res3 = parse_quantity("nan")
    assert res3.parse_status == "MISSING_QUANTITY"
    assert res3.parsed_quantity is None


# ---------------------------------------------------------------------------
# 2. Unit Normalization Tests
# ---------------------------------------------------------------------------
def test_kg_to_g_normalization():
    """Test kg normalization."""
    assert normalize_unit("kg") == "kg"
    assert normalize_unit("kilogram") == "kg"
    assert normalize_unit("kilograms") == "kg"


def test_grams_normalization():
    """Test grams normalization."""
    assert normalize_unit("g") == "g"
    assert normalize_unit("gram") == "g"
    assert normalize_unit("grams") == "g"


def test_cup_normalization():
    """Test cup normalization."""
    assert normalize_unit("cup") == "cup"
    assert normalize_unit("cups") == "cup"


def test_tablespoon_normalization():
    """Test tablespoon normalization."""
    assert normalize_unit("tablespoon") == "tbsp"
    assert normalize_unit("tablespoons") == "tbsp"
    assert normalize_unit("tbsp") == "tbsp"


def test_teaspoon_normalization():
    """Test teaspoon normalization."""
    assert normalize_unit("teaspoon") == "tsp"
    assert normalize_unit("teaspoons") == "tsp"
    assert normalize_unit("tsp") == "tsp"


# ---------------------------------------------------------------------------
# 3. Measure Converter Tests
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def converter():
    return MeasureConverter()


def test_cnf_food_specific_conversion(converter):
    """Test food-specific volume conversions without generic density."""
    # Rice (Food 4471): 1 cup = 195.478 g
    res_rice = converter.convert(
        food_code=4471,
        quantity=1.0,
        normalized_unit="cup",
    )
    assert res_rice.conversion_status == "CNF_MEASURE"
    assert res_rice.grams == 195.478

    # Moong Dal (Food 3362): 1 cup = 154.269 g
    res_dal = converter.convert(
        food_code=3362,
        quantity=1.0,
        normalized_unit="cup",
    )
    assert res_dal.conversion_status == "CNF_MEASURE"
    assert res_dal.grams == 154.269

    # Toor Dal (Food 3381): 1 cup = 194.421 g
    res_toor = converter.convert(
        food_code=3381,
        quantity=1.0,
        normalized_unit="cup",
    )
    assert res_toor.conversion_status == "CNF_MEASURE"
    assert res_toor.grams == 194.421

    # Sunflower oil (Food 7191): 1 tbsp = 13.82 g, 1 tsp = 4.607 g
    res_oil_tbsp = converter.convert(
        food_code=7191,
        quantity=1.0,
        normalized_unit="tbsp",
    )
    assert res_oil_tbsp.conversion_status == "CNF_MEASURE"
    assert res_oil_tbsp.grams == 13.82

    res_oil_tsp = converter.convert(
        food_code=7191,
        quantity=1.0,
        normalized_unit="tsp",
    )
    assert res_oil_tsp.conversion_status == "CNF_MEASURE"
    assert res_oil_tsp.grams == 4.607

    # Garlic (Food 2394): 1 clove = 3.0 g
    res_garlic = converter.convert(
        food_code=2394,
        quantity=2.0,
        normalized_unit="clove",
    )
    assert res_garlic.conversion_status == "CNF_MEASURE"
    assert res_garlic.grams == 6.0


def test_mass_conversion(converter):
    """Test direct mass conversion."""
    res_g = converter.convert(food_code=4471, quantity=150.0, normalized_unit="g")
    assert res_g.conversion_status == "DIRECT_MASS"
    assert res_g.grams == 150.0

    res_kg = converter.convert(food_code=4471, quantity=1.5, normalized_unit="kg")
    assert res_kg.conversion_status == "DIRECT_MASS"
    assert res_kg.grams == 1500.0


def test_qualitative_quantity(converter):
    """Test qualitative quantities like to taste or as required."""
    res1 = converter.convert(
        food_code=214,
        quantity=None,
        normalized_unit=None,
        original_ingredient="Salt - to taste",
        preparation="to taste",
    )
    assert res1.conversion_status == "QUALITATIVE_QUANTITY"
    assert res1.grams is None

    res2 = converter.convert(
        food_code=7191,
        quantity=None,
        normalized_unit=None,
        original_ingredient="Sunflower Oil - as required",
        preparation="as required",
    )
    assert res2.conversion_status == "QUALITATIVE_QUANTITY"
    assert res2.grams is None

    res3 = converter.convert(
        food_code=211,
        quantity=None,
        normalized_unit=None,
        original_ingredient="turmeric powder - a pinch",
        preparation="a pinch",
    )
    assert res3.conversion_status == "QUALITATIVE_QUANTITY"
    assert res3.grams is None


def test_no_match_mapping(converter):
    """Test NO_MATCH mapping status."""
    res = converter.convert(
        food_code=None,
        quantity=1.0,
        normalized_unit="tsp",
        mapping_quality="NO_MATCH",
    )
    assert res.conversion_status == "NO_MATCH"
    assert res.grams is None


def test_unmapped_ingredient(converter):
    """Test UNMAPPED recipe ingredient."""
    res = converter.convert(
        food_code=None,
        quantity=2.0,
        normalized_unit="tbsp",
        mapping_quality="UNMAPPED",
    )
    assert res.conversion_status == "UNMAPPED"
    assert res.grams is None


def test_water_handling(converter):
    """Test water preservation with 0 nutritional contribution."""
    res = converter.convert(
        food_code=2933,
        quantity=2.0,
        normalized_unit="cup",
        is_water=True,
    )
    assert res.conversion_status == "WATER"
    assert res.grams == 500.0


# ---------------------------------------------------------------------------
# 4. Nutrient Lookup Tests
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def lookup():
    return NutrientLookup()


def test_per_100g_nutrient_calculation(lookup):
    """Test scaling nutrients from 100g basis."""
    # Test food 7191 (Sunflower oil)
    prof_100g = lookup.get_profile_per_100g(7191)
    assert prof_100g is not None
    assert prof_100g.fat_g == 100.0

    # 15g of oil (approx 1 tbsp)
    calc = lookup.calculate_nutrients(7191, grams=15.0)
    assert calc.fat_g == 15.0
    assert calc.protein_g == 0.0
    assert calc.carbs_g == 0.0

    # 50g
    calc_50 = lookup.calculate_nutrients(7191, grams=50.0)
    assert calc_50.fat_g == 50.0


def test_nutrient_profile_operations():
    """Test NutrientProfile addition and division."""
    p1 = NutrientProfile(energy_kcal=100.0, protein_g=10.0, fat_g=5.0)
    p2 = NutrientProfile(energy_kcal=200.0, protein_g=20.0, fat_g=10.0)
    summed = p1.add(p2)

    assert summed.energy_kcal == 300.0
    assert summed.protein_g == 30.0
    assert summed.fat_g == 15.0

    # Per serving division
    per_serv = summed.divide(2.0)
    assert per_serv.energy_kcal == 150.0
    assert per_serv.protein_g == 15.0
    assert per_serv.fat_g == 7.5


def test_invalid_servings():
    """Test invalid servings error raising."""
    p = NutrientProfile(energy_kcal=100.0)
    with pytest.raises(ValueError):
        p.divide(0)

    with pytest.raises(ValueError):
        p.divide(-1)


# ---------------------------------------------------------------------------
# 5. Recipe Nutrition Engine Integration Tests
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def engine():
    return RecipeNutritionEngine()


def test_needs_review_curation_mapping(engine):
    """Test NEEDS_REVIEW mapping marked APPROXIMATE."""
    # ING00030: cinnamon stick -> CNF 178 (ground cinnamon) - NEEDS_REVIEW
    cur_info = engine._curated_map.get("ING00030")
    assert cur_info["curation_status"] == "NEEDS_REVIEW"
    assert cur_info["cnf_food_code"] == 178


def test_state_mismatch_detection(engine):
    """Test cooked vs dry grain/pulse state mismatch detection."""
    # Test cooked rice with dry CNF food
    dummy_row = {
        "recipe_id": "TEST_R1",
        "original_ingredient": "2 cups rice - cooked",
        "ingredient": "rice",
        "quantity": "2",
        "unit": "cups",
        "preparation": "cooked",
        "ingredient_id": "ING00099",
        "canonical_ingredient": "rice",
        "mapping_status": "MAPPED_CANONICAL",
    }
    processed = engine._process_ingredient_row(dummy_row)
    assert processed["state_status"] == "STATE_MISMATCH"
    assert processed["conversion_status"] == "STATE_MISMATCH"
    assert processed["nutrition_quality"] == "UNAVAILABLE"
    assert "State mismatch" in processed["calculation_notes"]
