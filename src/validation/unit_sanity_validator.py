"""Unit Sanity Validation Layer for KitchenPilot-V1.

Detects implausible, suspicious, or erroneous ingredient quantities (e.g. unit prefix typos,
extreme kilogram or liter quantities, extreme per-serving mass) before or after nutrition calculation.
Generates diagnostic audit file: data/mappings/unit_sanity_review.csv without mutating source data.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REVIEW_OUTPUT_PATH = PROJECT_ROOT / "data/mappings/unit_sanity_review.csv"

REVIEW_COLUMNS = [
    "recipe_id",
    "recipe_name",
    "original_ingredient",
    "quantity",
    "unit",
    "ingredient",
    "servings",
    "converted_mass_g",
    "per_serving_mass_g",
    "severity",
    "reason",
    "suggested_interpretation",
    "review_status",
]


class UnitSanityValidator:
    """Validates ingredient quantity and unit plausibility against culinary baselines."""

    def __init__(
        self,
        ingredient_nutrition_path: Path | str = PROJECT_ROOT / "data/processed/recipe_ingredient_nutrition.csv",
        recipes_path: Path | str = PROJECT_ROOT / "data/processed/recipes.csv",
    ) -> None:
        self.ingredient_nutrition_path = Path(ingredient_nutrition_path)
        self.recipes_path = Path(recipes_path)

    def validate(self) -> pd.DataFrame:
        """Run validation rules across all ingredient rows and return flagged anomalies."""
        ing_df = pd.read_csv(self.ingredient_nutrition_path, low_memory=False)
        rec_df = pd.read_csv(self.recipes_path, low_memory=False)

        merged = ing_df.merge(
            rec_df[["recipe_id", "recipe_name", "servings"]],
            on="recipe_id",
            how="left",
            suffixes=("", "_recipe"),
        )

        flagged_records: List[Dict[str, any]] = []

        # Load quality_checked status if available
        qc_path = PROJECT_ROOT / "data/processed/recipe_ingredients_quality_checked.csv"
        qc_status_map = {}
        if qc_path.is_file():
            qc_df = pd.read_csv(qc_path)
            for _, qcr in qc_df.iterrows():
                qc_status_map[(str(qcr["recipe_id"]).strip(), str(qcr["original_ingredient"]).strip())] = str(qcr["quality_status"]).strip()

        for _, row in merged.iterrows():
            rid = str(row["recipe_id"]).strip()
            rname = str(row["recipe_name"]) if pd.notna(row["recipe_name"]) else ""
            orig = str(row["original_ingredient"]) if pd.notna(row["original_ingredient"]) else ""
            raw_qty = row.get("quantity")
            raw_unit = str(row.get("unit")) if pd.notna(row.get("unit")) else ""
            ing = str(row["ingredient"]) if pd.notna(row["ingredient"]) else ""
            servings_raw = row.get("servings")
            grams = float(row["grams"]) if pd.notna(row["grams"]) else None

            # Parse servings safely
            try:
                servings = float(servings_raw) if pd.notna(servings_raw) else 1.0
                if servings <= 0:
                    servings = 1.0
            except (ValueError, TypeError):
                servings = 1.0

            ps_mass = round(grams / servings, 2) if grams is not None else None

            # Source numeric quantity and unit
            from src.nutrition.quantity_parser import parse_quantity, normalize_unit
            src_qres = parse_quantity(raw_qty)
            src_norm_unit = normalize_unit(raw_unit)
            source_qty = src_qres.parsed_quantity

            parsed_qty = float(row["parsed_quantity"]) if pd.notna(row["parsed_quantity"]) else None
            norm_unit = str(row["normalized_unit"]).lower() if pd.notna(row["normalized_unit"]) else ""

            # Quality status determination
            row_qc_status = qc_status_map.get((rid, orig), "SANITY_REVIEW")
            status_tag = "CORRECTED_SOURCE_UNIT" if row_qc_status == "CORRECTED_SOURCE_UNIT" else "SANITY_REVIEW"

            # Check Rule 1: Catastrophic unit prefix typos in Kg (e.g. 750 Kg, 250 kg)
            if src_norm_unit == "kg" and source_qty is not None and source_qty >= 20.0:
                flagged_records.append({
                    "recipe_id": rid,
                    "recipe_name": rname,
                    "original_ingredient": orig,
                    "quantity": raw_qty,
                    "unit": raw_unit,
                    "ingredient": ing,
                    "servings": servings_raw,
                    "converted_mass_g": grams,
                    "per_serving_mass_g": ps_mass,
                    "severity": "CRITICAL",
                    "reason": f"Excessive mass in household recipe ({source_qty} kg); likely unit prefix error (kg instead of g)",
                    "suggested_interpretation": f"{source_qty} g",
                    "review_status": status_tag,
                })
                continue

            # Check Rule 2: Catastrophic unit prefix typos in Liter (e.g. 200 liter)
            if src_norm_unit in ("liter", "l") and source_qty is not None and source_qty >= 20.0:
                flagged_records.append({
                    "recipe_id": rid,
                    "recipe_name": rname,
                    "original_ingredient": orig,
                    "quantity": raw_qty,
                    "unit": raw_unit,
                    "ingredient": ing,
                    "servings": servings_raw,
                    "converted_mass_g": grams,
                    "per_serving_mass_g": ps_mass,
                    "severity": "CRITICAL",
                    "reason": f"Excessive volume in household recipe ({source_qty} liters); likely unit prefix error (liter instead of ml)",
                    "suggested_interpretation": f"{source_qty} ml",
                    "review_status": status_tag,
                })
                continue

            # Check Rule 3: Single ingredient mass per serving > 2,500g
            if ps_mass is not None and ps_mass > 2500.0:
                flagged_records.append({
                    "recipe_id": rid,
                    "recipe_name": rname,
                    "original_ingredient": orig,
                    "quantity": raw_qty,
                    "unit": raw_unit,
                    "ingredient": ing,
                    "servings": servings_raw,
                    "converted_mass_g": grams,
                    "per_serving_mass_g": ps_mass,
                    "severity": "CRITICAL",
                    "reason": f"Implausible single-ingredient mass per serving ({ps_mass} g/serving)",
                    "suggested_interpretation": "Verify serving count or unit scaling",
                    "review_status": status_tag,
                })
                continue

            # Check Rule 4: Moderate excessive volume/mass (kg >= 5.0 or liter >= 5.0 for servings <= 6)
            if servings <= 6:
                if norm_unit == "kg" and parsed_qty is not None and parsed_qty >= 5.0:
                    flagged_records.append({
                        "recipe_id": rid,
                        "recipe_name": rname,
                        "original_ingredient": orig,
                        "quantity": raw_qty,
                        "unit": raw_unit,
                        "ingredient": ing,
                        "servings": servings_raw,
                        "converted_mass_g": grams,
                        "per_serving_mass_g": ps_mass,
                        "severity": "HIGH",
                        "reason": f"High bulk mass ({parsed_qty} kg) for small household serving size ({servings_raw})",
                        "suggested_interpretation": "Verify recipe batch scale or unit multiplier",
                        "review_status": status_tag,
                    })
                    continue
                if norm_unit == "liter" and parsed_qty is not None and parsed_qty >= 5.0:
                    flagged_records.append({
                        "recipe_id": rid,
                        "recipe_name": rname,
                        "original_ingredient": orig,
                        "quantity": raw_qty,
                        "unit": raw_unit,
                        "ingredient": ing,
                        "servings": servings_raw,
                        "converted_mass_g": grams,
                        "per_serving_mass_g": ps_mass,
                        "severity": "HIGH",
                        "reason": f"High liquid volume ({parsed_qty} liters) for small household serving size ({servings_raw})",
                        "suggested_interpretation": "Verify recipe batch scale or unit multiplier",
                        "review_status": status_tag,
                    })
                    continue

            # Check Rule 5: Per-serving single ingredient mass between 1,200g and 2,500g
            if ps_mass is not None and ps_mass > 1200.0:
                flagged_records.append({
                    "recipe_id": rid,
                    "recipe_name": rname,
                    "original_ingredient": orig,
                    "quantity": raw_qty,
                    "unit": raw_unit,
                    "ingredient": ing,
                    "servings": servings_raw,
                    "converted_mass_g": grams,
                    "per_serving_mass_g": ps_mass,
                    "severity": "MEDIUM",
                    "reason": f"Unusually high single-ingredient mass per serving ({ps_mass} g/serving)",
                    "suggested_interpretation": "Confirm if intended for whole meal batch or multi-portion item",
                    "review_status": status_tag,
                })
                continue

        review_df = pd.DataFrame(flagged_records, columns=REVIEW_COLUMNS)
        return review_df

    def run_and_save(self, output_path: Path | str = REVIEW_OUTPUT_PATH) -> pd.DataFrame:
        """Run validation and save review table to CSV."""
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        review_df = self.validate()
        review_df.to_csv(out_p, index=False)
        return review_df


def main() -> None:
    print("=" * 50)
    print("UNIT SANITY VALIDATOR")
    print("=" * 50)
    validator = UnitSanityValidator()
    review_df = validator.run_and_save()
    print(f"Total flagged ingredient rows: {len(review_df)}")
    print("Breakdown by severity:")
    print(review_df["severity"].value_counts())
    print(f"\nReview report written to: {REVIEW_OUTPUT_PATH}")
    print("=" * 50)


if __name__ == "__main__":
    main()
