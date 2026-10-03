"""Audit Suspicious Discrete Measures for KitchenPilot-V1.

Audits count-based and discrete ingredients (peppercorns, almonds, cashews,
pistachios, tomatoes, onions, chillies, garlic, ginger, cinnamon, bay leaves,
cloves, cardamom, dates, raisins, etc.) to ensure:
1. No arbitrary count uses a generic volumetric/container measure (100 ml, 100 ml whole,
   100 ml packed, container, etc.).
2. The discrete conversion priority hierarchy is strictly adhered to:
   - Explicit culinary item-mass default
   - Genuine CNF discrete item measure (1 item, 1 pepper, 1 whole, 1 medium, 1 fruit, 1 slice)
   - Ingredient-specific validated conversion / proxy
   - Otherwise UNAVAILABLE.

Produces data/mappings/suspicious_discrete_measure_review.csv with columns:
recipe_id, original_ingredient, ingredient_id, canonical_ingredient, quantity, unit,
cnf_food_code, cnf_food_name, selected_measure, grams, decision, reason, confidence
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.nutrition.measure_converter import MeasureConverter
from src.nutrition.quantity_parser import normalize_unit, parse_quantity

REVIEW_CSV_PATH = PROJECT_ROOT / "data" / "mappings" / "suspicious_discrete_measure_review.csv"
LINKED_PATH = PROJECT_ROOT / "data" / "processed" / "recipe_ingredients_linked.csv"
CURATED_PATH = PROJECT_ROOT / "data" / "mappings" / "cnf_ingredient_mapping_curated.csv"
OUTPUT_NUTRITION_PATH = PROJECT_ROOT / "data" / "processed" / "recipe_ingredient_nutrition.csv"

TARGET_DISCRETE_PATTERNS = re.compile(
    r"\b(peppercorn|peppercorns|pepper|almond|almonds|cashew|cashews|pistachio|pistachios|"
    r"tomato|tomatoes|onion|onions|chilli|chillies|chili|chilies|garlic|ginger|cinnamon|"
    r"bay\s*leaf|bay\s*leaves|clove|cloves|cardamom|cardamoms|date|dates|raisin|raisins)\b",
    re.IGNORECASE,
)

UNSAFE_VOL_PATTERNS = re.compile(
    r"\b(100\s*ml|100\s*ml\s*whole|100\s*ml\s*packed|125\s*ml\s*packed|250\s*ml\s*packed|"
    r"container|individual\s*container)\b",
    re.IGNORECASE,
)


def run_discrete_measures_audit() -> Tuple[pd.DataFrame, int]:
    """Execute audit across all discrete/count ingredients and verify zero unsafe conversions."""
    ril_df = pd.read_csv(LINKED_PATH)
    cur_df = pd.read_csv(CURATED_PATH)

    # Curated lookup
    cur_map: Dict[str, Tuple[Optional[int], Optional[str]]] = {}
    for _, row in cur_df.iterrows():
        iid = str(row["ingredient_id"]).strip()
        fc = int(row["cnf_food_code"]) if pd.notna(row["cnf_food_code"]) else None
        fname = str(row["cnf_food_name"]).strip() if pd.notna(row["cnf_food_name"]) else None
        cur_map[iid] = (fc, fname)

    converter = MeasureConverter()
    review_rows: List[Dict[str, any]] = []

    for _, row in ril_df.iterrows():
        rid = str(row["recipe_id"]).strip()
        orig_ing = str(row["original_ingredient"]) if pd.notna(row.get("original_ingredient")) else ""
        raw_qty = row.get("quantity")
        raw_unit = row.get("unit")
        iid = str(row["ingredient_id"]).strip() if pd.notna(row.get("ingredient_id")) else None
        canon = str(row["canonical_ingredient"]).strip() if pd.notna(row.get("canonical_ingredient")) else ""

        qres = parse_quantity(raw_qty)
        norm_unit = normalize_unit(raw_unit)

        is_count_unit = (norm_unit in (None, "piece"))
        matches_target_discrete = bool(TARGET_DISCRETE_PATTERNS.search(orig_ing) or TARGET_DISCRETE_PATTERNS.search(canon))

        fc, fname = cur_map.get(iid, (None, None))
        cnf_measures = converter._food_measures.get(fc, []) if fc is not None else []
        has_suspicious_cnf_measure = any(UNSAFE_VOL_PATTERNS.search(m[1]) for m in cnf_measures)

        # Include if it is a discrete/count item matching target discrete ingredients or food with suspicious CNF measure
        if not (is_count_unit and (matches_target_discrete or has_suspicious_cnf_measure)):
            continue

        if qres.parsed_quantity is None:
            continue

        cres = converter.convert(
            food_code=fc,
            quantity=qres.parsed_quantity,
            normalized_unit=norm_unit,
            original_ingredient=orig_ing,
            preparation="",
            is_water=False,
            mapping_quality="APPROVED" if fc is not None else "UNMAPPED",
            canonical_ingredient=canon,
        )

        # Identify selected measure or reason for rejection
        calc_notes = cres.notes or ""
        grams = cres.grams

        if cres.conversion_status == "CNF_MEASURE":
            if "calibration" in calc_notes.lower():
                decision = "EXACT_CALIBRATION"
                selected_measure = calc_notes
                confidence = "HIGH"
                reason = "Discrete item converted using validated culinary item-mass default"
            elif "override" in calc_notes.lower():
                decision = "APPROXIMATE_PROXY"
                selected_measure = calc_notes
                confidence = "HIGH"
                reason = "Converted using validated ingredient-specific measure override"
            else:
                decision = "EXACT_CNF_DISCRETE"
                selected_measure = calc_notes
                confidence = "HIGH"
                reason = "Converted using genuine CNF discrete item measure (whole/medium/item/fruit/pepper/slice)"
        else:
            decision = "UNAVAILABLE"
            confidence = "UNAVAILABLE"
            if has_suspicious_cnf_measure:
                selected_measure = "REJECTED_CONTAINER_MEASURE"
                reason = "CNF container/volumetric measure (100 ml whole/packed) strictly excluded for discrete count; withheld pending item calibration"
            else:
                selected_measure = "NONE"
                reason = f"No genuine discrete measure or calibration available in CNF ({calc_notes})"

        review_rows.append({
            "recipe_id": rid,
            "original_ingredient": orig_ing,
            "ingredient_id": iid,
            "canonical_ingredient": canon,
            "quantity": raw_qty,
            "unit": raw_unit,
            "cnf_food_code": fc,
            "cnf_food_name": fname,
            "selected_measure": selected_measure,
            "grams": grams,
            "decision": decision,
            "reason": reason,
            "confidence": confidence,
        })

    review_df = pd.DataFrame(review_rows, columns=[
        "recipe_id",
        "original_ingredient",
        "ingredient_id",
        "canonical_ingredient",
        "quantity",
        "unit",
        "cnf_food_code",
        "cnf_food_name",
        "selected_measure",
        "grams",
        "decision",
        "reason",
        "confidence",
    ])

    REVIEW_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    review_df.to_csv(REVIEW_CSV_PATH, index=False)

    # Global scan on output dataset for any remaining unsafe count->volume conversions
    unsafe_violations = 0
    if OUTPUT_NUTRITION_PATH.is_file():
        out_df = pd.read_csv(OUTPUT_NUTRITION_PATH, low_memory=False)
        count_rows = out_df[out_df["unit"].isna() | (out_df["unit"] == "piece")]
        unsafe_mask = count_rows["calculation_notes"].str.contains(
            r"\b(?:100\s*ml\s*whole|100\s*ml\s*packed|100\s*ml\s*container|125\s*ml\s*packed|250\s*ml\s*packed)\b",
            case=False,
            na=False,
        )
        unsafe_violations = int(unsafe_mask.sum())

    print(f"Generated {REVIEW_CSV_PATH} with {len(review_df)} audited discrete/count rows.")
    print(f"Global safety audit - Unsafe count->volume conversions found: {unsafe_violations}")

    return review_df, unsafe_violations


if __name__ == "__main__":
    _, violations = run_discrete_measures_audit()
    if violations > 0:
        print(f"FAILED: Found {violations} unsafe count->volume conversions!")
        sys.exit(1)
    else:
        print("PASSED: 0 unsafe count->volume conversions found.")
