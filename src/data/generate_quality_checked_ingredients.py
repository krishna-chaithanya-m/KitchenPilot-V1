"""Generates data/processed/recipe_ingredients_quality_checked.csv.

Preserves the original source data while creating a derived, quality-checked
representation with effective quantities and units for high-confidence corrections.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RIL_PATH = PROJECT_ROOT / "data/processed/recipe_ingredients_linked.csv"
RECIPES_PATH = PROJECT_ROOT / "data/processed/recipes.csv"
OUTPUT_PATH = PROJECT_ROOT / "data/processed/recipe_ingredients_quality_checked.csv"


def generate_quality_checked() -> pd.DataFrame:
    ril_df = pd.read_csv(RIL_PATH)
    rec_df = pd.read_csv(RECIPES_PATH)

    # Merge recipe metadata
    merged = ril_df.merge(
        rec_df[["recipe_id", "recipe_name", "servings"]],
        on="recipe_id",
        how="left",
    )

    # Prepare fields
    effective_quantities = []
    effective_units = []
    quality_statuses = []
    correction_types = []
    correction_reasons = []
    correction_confidences = []
    correction_sources = []

    for _, row in merged.iterrows():
        rid = str(row["recipe_id"]).strip()
        orig_qty = row["quantity"]
        orig_unit = row["unit"]
        orig_ing = str(row["original_ingredient"]) if pd.notna(row["original_ingredient"]) else ""

        # Check high-confidence unit prefix corrections
        if rid == "R05587" and "750" in str(orig_qty) and "kg" in str(orig_unit).lower():
            effective_quantities.append("750")
            effective_units.append("g")
            quality_statuses.append("CORRECTED_SOURCE_UNIT")
            correction_types.append("UNIT_PREFIX_CORRECTION")
            correction_reasons.append("Unit prefix typo (kg instead of g) for household chicken curry")
            correction_confidences.append("HIGH")
            correction_sources.append("CULINARY_VALIDATION")
        elif rid == "R07106" and "200" in str(orig_qty) and "liter" in str(orig_unit).lower():
            effective_quantities.append("200")
            effective_units.append("ml")
            quality_statuses.append("CORRECTED_SOURCE_UNIT")
            correction_types.append("UNIT_PREFIX_CORRECTION")
            correction_reasons.append("Unit prefix typo (liter instead of ml) for coconut milk curry")
            correction_confidences.append("HIGH")
            correction_sources.append("CULINARY_VALIDATION")
        elif rid == "R10172" and "250" in str(orig_qty) and "kg" in str(orig_unit).lower():
            effective_quantities.append("250")
            effective_units.append("g")
            quality_statuses.append("CORRECTED_SOURCE_UNIT")
            correction_types.append("UNIT_PREFIX_CORRECTION")
            correction_reasons.append("Unit prefix typo (kg instead of g) for mocktail beverage")
            correction_confidences.append("HIGH")
            correction_sources.append("CULINARY_VALIDATION")

        # Check medium/low confidence sanity review cases
        elif rid == "R01075" and "10" in str(orig_qty) and "kilogram" in str(orig_unit).lower():
            effective_quantities.append(orig_qty)
            effective_units.append(orig_unit)
            quality_statuses.append("SANITY_REVIEW")
            correction_types.append("NONE")
            correction_reasons.append("High bulk mass (10 kg) for small household serving size; pending culinary review")
            correction_confidences.append("MEDIUM")
            correction_sources.append("SANITY_VALIDATOR")
        elif rid == "R03199" and "10" in str(orig_qty) and "cup" in str(orig_unit).lower():
            effective_quantities.append(orig_qty)
            effective_units.append(orig_unit)
            quality_statuses.append("SANITY_REVIEW")
            correction_types.append("NONE")
            correction_reasons.append("Unusually high single-ingredient mass per serving (1250g/serv water)")
            correction_confidences.append("LOW")
            correction_sources.append("SANITY_VALIDATOR")
        elif rid == "R06930" and "12" in str(orig_qty) and "cucumber" in orig_ing.lower():
            effective_quantities.append(orig_qty)
            effective_units.append(orig_unit)
            quality_statuses.append("SANITY_REVIEW")
            correction_types.append("NONE")
            correction_reasons.append("High single-ingredient mass per serving (1806g/serv cucumber)")
            correction_confidences.append("LOW")
            correction_sources.append("SANITY_VALIDATOR")
        elif rid == "R09767" and "12" in str(orig_qty) and "cauliflower" in orig_ing.lower():
            effective_quantities.append(orig_qty)
            effective_units.append(orig_unit)
            quality_statuses.append("SANITY_REVIEW")
            correction_types.append("NONE")
            correction_reasons.append("High single-ingredient mass per serving (3450g/serv cauliflower)")
            correction_confidences.append("LOW")
            correction_sources.append("SANITY_VALIDATOR")

        # Standard uncorrected rows
        else:
            effective_quantities.append(orig_qty)
            effective_units.append(orig_unit)
            quality_statuses.append("ORIGINAL")
            correction_types.append("NONE")
            correction_reasons.append("NONE")
            correction_confidences.append("HIGH")
            correction_sources.append("SOURCE_DATA")

    merged["original_quantity"] = merged["quantity"]
    merged["original_unit"] = merged["unit"]
    merged["effective_quantity"] = effective_quantities
    merged["effective_unit"] = effective_units
    merged["quality_status"] = quality_statuses
    merged["correction_type"] = correction_types
    merged["correction_reason"] = correction_reasons
    merged["correction_confidence"] = correction_confidences
    merged["correction_source"] = correction_sources

    # Ensure quantity and unit aliases match original_quantity and original_unit
    merged["quantity"] = merged["original_quantity"]
    merged["unit"] = merged["original_unit"]

    # Required column order
    cols = [
        "recipe_id",
        "recipe_name",
        "original_ingredient",
        "original_quantity",
        "original_unit",
        "quantity",
        "unit",
        "ingredient",
        "servings",
        "preparation",
        "ingredient_id",
        "canonical_ingredient",
        "mapping_status",
        "effective_quantity",
        "effective_unit",
        "quality_status",
        "correction_type",
        "correction_reason",
        "correction_confidence",
        "correction_source",
    ]
    out_df = merged[cols]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUTPUT_PATH, index=False)
    print(f"Generated {OUTPUT_PATH} with {len(out_df)} rows.")
    print("Quality status distribution:")
    print(out_df["quality_status"].value_counts())
    return out_df


if __name__ == "__main__":
    generate_quality_checked()
