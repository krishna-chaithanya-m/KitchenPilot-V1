"""Normalize the official Health Canada CNF 2026 relational CSV files.

NOTE: This script is an offline-only developer utility. The generated
data/processed/cnf_2026_nutrition.csv (~297 MB) is an intermediate artifact
that is intentionally excluded from Git. The runtime release and release test suite
do not require this output file.
"""

import re
from collections import Counter
from pathlib import Path

import pandas as pd


RAW_DIR = Path("data/raw/nutrition/cnf_2026")
OUTPUT_FILE = Path("data/processed/cnf_2026_nutrition.csv")
SOURCE = "CNF_2026"
SOURCE_LICENSE = "Open Government Licence - Canada 2.0"
SOURCE_REFERENCE = (
    "https://open.canada.ca/data/dataset/1b6139bd-ed7e-4043-bc28-ff00e10f3109"
)
BASIS = "per_100g_edible_portion"

RAW_TABLES = {
    "food_name": "food_name.csv",
    "food_source": "food_source.csv",
    "nutrient_amount": "nutrient_amount.csv",
    "nutrient_name": "nutrient_name.csv",
    "nutrient_source": "nutrient_source.csv",
    "measure_weight_conversion": "measure_weight_conversion.csv",
    "measure_type": "measure_type.csv",
    "measure_name": "measure_name.csv",
}

REQUIRED_COLUMNS = {
    "food_name": [
        "Food_Code",
        "Food_Description_EN",
        "Food_Description_FR",
        "Alternate_Description_EN",
        "Alternate_Description_FR",
        "Food_Source_Code",
        "USDA_NDB_Code",
        "CNF_Food_Group_Code",
        "Comment_EN",
        "Comment_FR",
        "ScientificName",
        "Food_Last_Updated_Date",
    ],
    "food_source": [
        "Food_Source_Code",
        "Food_Source_Description_EN",
        "Food_Source_Description_FR",
    ],
    "nutrient_amount": [
        "Food_Code",
        "Nutrient_Code",
        "Nutrient_Amount",
        "STD_Error",
        "Observations",
        "Nutrient_Source_Code",
        "Nutrient_Last_Updated_Date",
    ],
    "nutrient_name": [
        "Nutrient_Code",
        "Nutrient_Symbol",
        "Nutrient_Unit",
        "Nutrient_Name_EN",
        "Nutrient_Name_FR",
        "Tagname",
        "Nutrient_Decimals",
    ],
    "nutrient_source": [
        "Nutrient_Source_Code",
        "Nutrient_Source_Description_EN",
        "Nutrient_Source_Description_FR",
    ],
    "measure_weight_conversion": [
        "Food_Code",
        "Measure_Type_Code",
        "Measure_Code",
        "Measure_Weight_Conversion",
        "Measure_Weight_Conversion_Last_Updated_Date",
    ],
    "measure_type": [
        "Measure_Type_Code",
        "Measure_Type_Description_EN",
        "Measure_Type_Description_FR",
    ],
    "measure_name": [
        "Measure_Code",
        "Measure_Description_and_Unit_EN",
        "Measure_Description_and_Unit_FR",
    ],
}

CORE_NUTRIENT_NAMES = {
    "203": "protein_g",
    "204": "fat_g",
    "205": "carbs_g",
    "208": "energy_kcal",
    "268": "energy_kj",
    "269": "sugar_g",
    "291": "fiber_g",
    "307": "sodium_mg",
}

FORM_CUES = (
    "raw",
    "cooked",
    "boiled",
    "dry",
    "dried",
    "powder",
    "powdered",
    "ground",
    "roasted",
    "fried",
    "canned",
    "frozen",
    "dehydrated",
    "prepared",
    "steamed",
    "baked",
    "drained",
    "toasted",
)

OUTPUT_COLUMNS = [
    "source",
    "source_reference",
    "source_food_id",
    "food_name",
    "food_description",
    "food_form",
    "food_name_fr",
    "alternate_names_en",
    "alternate_names_fr",
    "scientific_name",
    "food_source_code",
    "food_source_description",
    "source_usda_ndb_code",
    "source_cnf_food_group_code",
    "source_food_last_updated_date",
    "nutrient_id",
    "source_nutrient_id",
    "nutrient_name",
    "nutrient_name_fr",
    "normalized_nutrient_name",
    "nutrient_symbol",
    "nutrient_tagname",
    "nutrient_value",
    "nutrient_unit",
    "nutrient_decimals",
    "standard_error",
    "observations",
    "nutrient_source_code",
    "nutrient_source_description",
    "source_date",
    "basis",
    "license",
]


def load_tables() -> dict[str, pd.DataFrame]:
    """Read and validate all downloaded tables without coercing IDs to numbers."""
    tables: dict[str, pd.DataFrame] = {}
    for table_name, filename in RAW_TABLES.items():
        path = RAW_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required CNF 2026 file not found: {path}")
        frame = pd.read_csv(
            path, dtype="string", keep_default_na=False, encoding="utf-8-sig"
        )
        missing = [
            column for column in REQUIRED_COLUMNS[table_name] if column not in frame
        ]
        if missing:
            raise ValueError(
                f"{path} is missing required column(s): {', '.join(missing)}"
            )
        if frame.empty:
            raise ValueError(f"CNF 2026 table is empty: {path}")
        tables[table_name] = frame
    return tables


def _require_unique(frame: pd.DataFrame, column: str, table_name: str) -> None:
    if frame[column].eq("").any():
        raise ValueError(f"{table_name}.{column} contains blank IDs")
    duplicates = frame.loc[frame[column].duplicated(), column].unique().tolist()
    if duplicates:
        raise ValueError(
            f"{table_name}.{column} contains duplicate IDs: {duplicates[:10]}"
        )


def normalize_nutrient_name(nutrient_code: str, nutrient_name: str) -> str:
    """Map required nutrients by CNF ID; retain a stable label for all others."""
    if nutrient_code in CORE_NUTRIENT_NAMES:
        return CORE_NUTRIENT_NAMES[nutrient_code]

    slug = re.sub(r"[^a-z0-9]+", "_", nutrient_name.casefold()).strip("_")
    return f"cnf_{slug}_{nutrient_code}"


def classify_food_form(description: str) -> str:
    """Tag form words in the exact CNF description; never merge food records."""
    normalized = description.casefold()
    matched = [
        cue for cue in FORM_CUES if re.search(rf"\b{re.escape(cue)}\b", normalized)
    ]
    return ";".join(matched) if matched else "unspecified_in_description"


def _numeric_column(frame: pd.DataFrame, column: str, table_name: str) -> pd.Series:
    raw_values = frame[column].astype("string")
    numeric_values = pd.to_numeric(raw_values.mask(raw_values.eq("")), errors="coerce")
    invalid = raw_values.ne("") & numeric_values.isna()
    if invalid.any():
        examples = raw_values[invalid].head(5).tolist()
        raise ValueError(
            f"{table_name}.{column} contains non-numeric values: {examples}"
        )
    return numeric_values


def build_normalized_table(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Join CNF's relational records at one row per food/nutrient value."""
    foods = tables["food_name"].copy()
    nutrients = tables["nutrient_name"].copy()
    amounts = tables["nutrient_amount"].copy()
    food_sources = tables["food_source"].copy()
    nutrient_sources = tables["nutrient_source"].copy()

    _require_unique(foods, "Food_Code", "food_name")
    _require_unique(nutrients, "Nutrient_Code", "nutrient_name")
    _require_unique(food_sources, "Food_Source_Code", "food_source")
    _require_unique(nutrient_sources, "Nutrient_Source_Code", "nutrient_source")

    foods["Food_Form"] = foods["Food_Description_EN"].map(classify_food_form)
    foods["Food_Description"] = foods["Comment_EN"]
    foods["food_source_code"] = foods["Food_Source_Code"]
    nutrients["nutrient_source_code"] = nutrients["Nutrient_Code"]
    amounts["Nutrient_Amount"] = _numeric_column(
        amounts, "Nutrient_Amount", "nutrient_amount"
    )
    amounts["STD_Error"] = _numeric_column(amounts, "STD_Error", "nutrient_amount")
    amounts["Observations"] = _numeric_column(
        amounts, "Observations", "nutrient_amount"
    )

    merged = amounts.merge(
        foods,
        on="Food_Code",
        how="left",
        validate="many_to_one",
        indicator="_food_merge",
    )
    missing_foods = merged["_food_merge"].ne("both")
    if missing_foods.any():
        missing_ids = merged.loc[missing_foods, "Food_Code"].unique().tolist()
        raise ValueError(
            f"Nutrient amounts reference unknown food IDs: {missing_ids[:10]}"
        )
    merged = merged.drop(columns="_food_merge")

    merged = merged.merge(
        nutrients,
        on="Nutrient_Code",
        how="left",
        validate="many_to_one",
        indicator="_nutrient_merge",
    )
    missing_nutrients = merged["_nutrient_merge"].ne("both")
    if missing_nutrients.any():
        missing_ids = merged.loc[missing_nutrients, "Nutrient_Code"].unique().tolist()
        raise ValueError(
            f"Nutrient amounts reference unknown nutrient IDs: {missing_ids[:10]}"
        )
    merged = merged.drop(columns="_nutrient_merge")

    merged = merged.merge(
        food_sources,
        on="Food_Source_Code",
        how="left",
        validate="many_to_one",
        indicator="_food_source_merge",
    )
    missing_food_sources = merged["_food_source_merge"].ne("both")
    if missing_food_sources.any():
        missing_codes = (
            merged.loc[missing_food_sources, "Food_Source_Code"].unique().tolist()
        )
        raise ValueError(f"Unknown food-source codes: {missing_codes[:10]}")
    merged = merged.drop(columns="_food_source_merge")

    merged = merged.merge(
        nutrient_sources,
        on="Nutrient_Source_Code",
        how="left",
        validate="many_to_one",
        indicator="_nutrient_source_merge",
    )
    missing_nutrient_sources = merged["_nutrient_source_merge"].ne("both")
    if missing_nutrient_sources.any():
        missing_codes = (
            merged.loc[missing_nutrient_sources, "Nutrient_Source_Code"]
            .unique()
            .tolist()
        )
        raise ValueError(f"Unknown nutrient-source codes: {missing_codes[:10]}")
    merged = merged.drop(columns="_nutrient_source_merge")

    merged["Nutrient_Code"] = merged["Nutrient_Code"].astype("string")
    normalized = pd.DataFrame(
        {
            "source": SOURCE,
            "source_reference": SOURCE_REFERENCE,
            "source_food_id": merged["Food_Code"],
            "food_name": merged["Food_Description_EN"],
            "food_description": merged["Food_Description"],
            "food_form": merged["Food_Form"],
            "food_name_fr": merged["Food_Description_FR"],
            "alternate_names_en": merged["Alternate_Description_EN"],
            "alternate_names_fr": merged["Alternate_Description_FR"],
            "scientific_name": merged["ScientificName"],
            "food_source_code": merged["Food_Source_Code"],
            "food_source_description": merged["Food_Source_Description_EN"],
            "source_usda_ndb_code": merged["USDA_NDB_Code"],
            "source_cnf_food_group_code": merged["CNF_Food_Group_Code"],
            "source_food_last_updated_date": merged["Food_Last_Updated_Date"],
            "nutrient_id": merged["Nutrient_Code"],
            "source_nutrient_id": merged["Nutrient_Code"],
            "nutrient_name": merged["Nutrient_Name_EN"],
            "nutrient_name_fr": merged["Nutrient_Name_FR"],
            "normalized_nutrient_name": [
                normalize_nutrient_name(code, name)
                for code, name in zip(
                    merged["Nutrient_Code"], merged["Nutrient_Name_EN"]
                )
            ],
            "nutrient_symbol": merged["Nutrient_Symbol"],
            "nutrient_tagname": merged["Tagname"],
            "nutrient_value": merged["Nutrient_Amount"],
            "nutrient_unit": merged["Nutrient_Unit"],
            "nutrient_decimals": merged["Nutrient_Decimals"],
            "standard_error": merged["STD_Error"],
            "observations": merged["Observations"],
            "nutrient_source_code": merged["Nutrient_Source_Code"],
            "nutrient_source_description": merged["Nutrient_Source_Description_EN"],
            "source_date": merged["Nutrient_Last_Updated_Date"],
            "basis": BASIS,
            "license": SOURCE_LICENSE,
        },
        columns=OUTPUT_COLUMNS,
    )

    return normalized


def print_import_report(
    tables: dict[str, pd.DataFrame], normalized: pd.DataFrame
) -> None:
    food_forms = Counter(
        cue
        for value in tables["food_name"]["Food_Description_EN"]
        for cue in FORM_CUES
        if re.search(rf"\b{re.escape(cue)}\b", value.casefold())
    )
    print("=" * 50)
    print("CNF 2026 NUTRITION IMPORT")
    print("=" * 50)
    print(f"\nSource: Canadian Nutrient File 2026")
    print(f"License: {SOURCE_LICENSE}")
    print(f"\nFood records: {len(tables['food_name']):,}")
    print(f"Nutrient definitions: {len(tables['nutrient_name']):,}")
    print(f"Nutrient amount records: {len(tables['nutrient_amount']):,}")
    print(f"Measure records: {len(tables['measure_weight_conversion']):,}")
    print(f"\nNormalized nutrition rows: {len(normalized):,}")
    print(f"\nUnique foods: {normalized['source_food_id'].nunique():,}")
    print(f"Unique nutrients: {normalized['nutrient_id'].nunique():,}")
    print("\nFood forms detected:")
    for form, count in food_forms.most_common():
        print(f"{form}: {count:,}")
    print(f"\nOutput:\n{OUTPUT_FILE}")


def main() -> None:
    tables = load_tables()
    normalized = build_normalized_table(tables)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(OUTPUT_FILE, index=False, encoding="utf-8", na_rep="")
    print_import_report(tables, normalized)


if __name__ == "__main__":
    main()
