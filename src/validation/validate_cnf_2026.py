"""Validate the normalized CNF 2026 nutrition import against its source tables."""

from pathlib import Path

import pandas as pd


RAW_DIR = Path("data/raw/nutrition/cnf_2026")
NORMALIZED_FILE = Path("data/processed/cnf_2026_nutrition.csv")
EXPECTED_SOURCE = "CNF_2026"
EXPECTED_BASIS = "per_100g_edible_portion"
EXPECTED_LICENSE = "Open Government Licence - Canada 2.0"

RAW_FILES = {
    "food_name": "food_name.csv",
    "food_source": "food_source.csv",
    "nutrient_amount": "nutrient_amount.csv",
    "nutrient_name": "nutrient_name.csv",
    "nutrient_source": "nutrient_source.csv",
    "measure_weight_conversion": "measure_weight_conversion.csv",
    "measure_type": "measure_type.csv",
    "measure_name": "measure_name.csv",
}

REQUIRED_OUTPUT_COLUMNS = [
    "source",
    "source_reference",
    "source_food_id",
    "food_name",
    "food_form",
    "nutrient_id",
    "source_nutrient_id",
    "nutrient_name",
    "normalized_nutrient_name",
    "nutrient_value",
    "nutrient_unit",
    "standard_error",
    "observations",
    "nutrient_source_code",
    "source_food_last_updated_date",
    "source_date",
    "basis",
    "license",
]

FORM_CUES = (
    "raw",
    "cooked",
    "boiled",
    "dry",
    "dried",
    "powder",
    "ground",
    "roasted",
    "fried",
    "canned",
    "frozen",
    "prepared",
)


def _read_raw_tables() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    missing_files = [
        str(RAW_DIR / filename)
        for filename in RAW_FILES.values()
        if not (RAW_DIR / filename).is_file()
    ]
    if missing_files:
        raise FileNotFoundError(
            "Required CNF raw file(s) are missing: " + ", ".join(missing_files)
        )

    for table_name, filename in RAW_FILES.items():
        frame = pd.read_csv(
            RAW_DIR / filename,
            dtype="string",
            keep_default_na=False,
            encoding="utf-8-sig",
        )
        if frame.empty:
            raise ValueError(f"CNF raw table is empty: {RAW_DIR / filename}")
        tables[table_name] = frame
    return tables


def _assert_equal(left: pd.Series, right: pd.Series, label: str) -> None:
    left_values = left.fillna("").astype("string").reset_index(drop=True)
    right_values = right.fillna("").astype("string").reset_index(drop=True)
    if not left_values.equals(right_values):
        raise ValueError(f"Normalized data changed or lost source field: {label}")


def validate() -> dict[str, int]:
    if not NORMALIZED_FILE.is_file():
        raise FileNotFoundError(f"Normalized CNF table not found: {NORMALIZED_FILE}")

    tables = _read_raw_tables()
    normalized = pd.read_csv(
        NORMALIZED_FILE,
        dtype="string",
        keep_default_na=False,
        encoding="utf-8-sig",
        low_memory=False,
    )
    missing_columns = [
        column for column in REQUIRED_OUTPUT_COLUMNS if column not in normalized.columns
    ]
    if missing_columns:
        raise ValueError(
            "Normalized CNF table is missing required column(s): "
            + ", ".join(missing_columns)
        )

    foods = tables["food_name"]
    amounts = tables["nutrient_amount"]
    nutrient_names = tables["nutrient_name"]
    food_sources = tables["food_source"]
    nutrient_sources = tables["nutrient_source"]

    for frame, column, table_name in (
        (foods, "Food_Code", "food_name"),
        (nutrient_names, "Nutrient_Code", "nutrient_name"),
    ):
        if frame[column].eq("").any():
            raise ValueError(f"{table_name}.{column} has blank identifiers")
        if frame[column].duplicated().any():
            raise ValueError(f"{table_name}.{column} has duplicate identifiers")

    if len(normalized) != len(amounts):
        raise ValueError(
            f"Normalized row count {len(normalized):,} differs from source amount "
            f"row count {len(amounts):,}"
        )

    if normalized.duplicated(["source_food_id", "source_nutrient_id"]).any():
        raise ValueError("Normalized table has duplicate food/nutrient records")
    if amounts.duplicated(["Food_Code", "Nutrient_Code"]).any():
        raise ValueError("Source nutrient_amount has duplicate food/nutrient records")

    food_ids = set(foods["Food_Code"])
    nutrient_ids = set(nutrient_names["Nutrient_Code"])
    normalized_food_ids = set(normalized["source_food_id"])
    if normalized_food_ids != food_ids:
        raise ValueError("Normalized food IDs do not match CNF food_name IDs")
    if not set(amounts["Food_Code"]).issubset(food_ids):
        raise ValueError("CNF nutrient amounts reference unknown food IDs")
    if not set(amounts["Nutrient_Code"]).issubset(nutrient_ids):
        raise ValueError("CNF nutrient amounts reference unknown nutrient IDs")

    if not set(foods["Food_Source_Code"]).issubset(
        set(food_sources["Food_Source_Code"])
    ):
        raise ValueError("CNF food table contains unknown food-source codes")
    if not set(amounts["Nutrient_Source_Code"]).issubset(
        set(nutrient_sources["Nutrient_Source_Code"])
    ):
        raise ValueError("CNF nutrient amounts contain unknown nutrient-source codes")

    expected_values = amounts["Nutrient_Amount"].replace("", pd.NA)
    actual_values = normalized["nutrient_value"].replace("", pd.NA)
    expected_numeric = pd.to_numeric(expected_values, errors="coerce")
    actual_numeric = pd.to_numeric(actual_values, errors="coerce")
    if (expected_values.notna() & expected_numeric.isna()).any():
        raise ValueError("Source nutrient amounts contain non-numeric values")
    if (actual_values.notna() & actual_numeric.isna()).any():
        raise ValueError("Normalized nutrient values contain non-numeric values")
    if not expected_numeric.reset_index(drop=True).equals(
        actual_numeric.reset_index(drop=True)
    ):
        raise ValueError("Normalized nutrient values differ from source values")

    negative_count = int((actual_numeric < 0).sum())
    if negative_count:
        raise ValueError(f"Found {negative_count} negative nutrient value(s)")

    # Check nutrient units and source amounts against each original CNF code.
    nutrient_lookup = nutrient_names.set_index("Nutrient_Code")
    expected_units = normalized["nutrient_id"].map(nutrient_lookup["Nutrient_Unit"])
    _assert_equal(expected_units, normalized["nutrient_unit"], "nutrient_unit")
    _assert_equal(
        normalized["nutrient_id"], normalized["source_nutrient_id"], "nutrient ID"
    )

    food_lookup = foods.set_index("Food_Code")
    expected_names = normalized["source_food_id"].map(
        food_lookup["Food_Description_EN"]
    )
    _assert_equal(expected_names, normalized["food_name"], "Food_Description_EN")

    expected_source = amounts["Nutrient_Source_Code"].reset_index(drop=True)
    _assert_equal(
        expected_source, normalized["nutrient_source_code"], "Nutrient_Source_Code"
    )
    _assert_equal(
        amounts["Nutrient_Last_Updated_Date"],
        normalized["source_date"],
        "Nutrient_Last_Updated_Date",
    )

    if not normalized["source"].eq(EXPECTED_SOURCE).all():
        raise ValueError("Some records do not identify their source as CNF_2026")
    if not normalized["source_reference"].astype(bool).all():
        raise ValueError("Some records have no source_reference")
    if not normalized["license"].eq(EXPECTED_LICENSE).all():
        raise ValueError("Some records have an incorrect or missing license")
    if not normalized["basis"].eq(EXPECTED_BASIS).all():
        raise ValueError("Some records have an absent or unexpected nutrition basis")

    form_counts = {
        form: int(normalized["food_form"].str.contains(form, regex=False).sum())
        for form in FORM_CUES
    }
    absent_forms = [
        form
        for form in ("raw", "cooked", "boiled", "dry", "prepared")
        if not form_counts[form]
    ]
    if absent_forms:
        raise ValueError(
            "Expected food-form distinctions were not retained: "
            + ", ".join(absent_forms)
        )

    # Blank source amounts must remain blank, never replaced by zero.
    blank_source_values = int(amounts["Nutrient_Amount"].eq("").sum())
    blank_output_values = int(normalized["nutrient_value"].eq("").sum())
    if blank_source_values != blank_output_values:
        raise ValueError(
            "Blank nutrient amounts changed during normalization: "
            f"source={blank_source_values}, output={blank_output_values}"
        )

    return {
        "foods": len(foods),
        "nutrient_definitions": len(nutrient_names),
        "amount_records": len(amounts),
        "normalized_rows": len(normalized),
        "negative_values": negative_count,
        "blank_values": blank_output_values,
        "food_form_records": sum(form_counts.values()),
    }


def main() -> None:
    stats = validate()
    print("=" * 50)
    print("CNF 2026 VALIDATION")
    print("=" * 50)
    print("\nSource integrity: PASS")
    print("Nutrition values: PASS")
    print("Units: PASS")
    print("Basis: PASS")
    print("Food forms: PASS")
    print("Provenance: PASS")
    print("\nValidation result: PASS")
    print(
        f"\nFoods: {stats['foods']:,}; definitions: {stats['nutrient_definitions']:,}; "
        f"source/output amount rows: {stats['amount_records']:,}/{stats['normalized_rows']:,}"
    )
    print(
        f"Blank values preserved: {stats['blank_values']:,}; "
        f"negative values: {stats['negative_values']:,}"
    )
    print(f"\nValidated output:\n{NORMALIZED_FILE}")


if __name__ == "__main__":
    main()
