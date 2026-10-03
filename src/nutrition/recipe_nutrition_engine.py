"""Recipe Nutrition Calculation Engine for KitchenPilot-V1.

Deterministic calculation of recipe-level nutrition using curated CNF mappings,
food-specific measure conversions, and per-100g edible portion profiles.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.nutrition.measure_converter import MeasureConverter
from src.nutrition.nutrient_lookup import NutrientLookup, NutrientProfile
from src.nutrition.quantity_parser import normalize_unit, parse_quantity

COOKED_STATE_CUES = re.compile(
    r"\b(cooked|boiled|steamed|soaked)\b",
    re.IGNORECASE,
)

DRY_RAW_CNF_CUES = re.compile(
    r"\b(dry|raw)\b",
    re.IGNORECASE,
)

INGREDIENT_NUTRITION_COLUMNS = [
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

RECIPE_NUTRITION_COLUMNS = [
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


class RecipeNutritionEngine:
    """Orchestrates deterministic recipe nutrition calculation and aggregation."""

    def __init__(
        self,
        recipes_path: Path | str = "data/processed/recipes.csv",
        linked_ingredients_path: Path | str = "data/processed/recipe_ingredients_linked.csv",
        curated_mapping_path: Path | str = "data/mappings/cnf_ingredient_mapping_curated.csv",
        cnf_nutrition_path: Path | str = "data/processed/cnf_2026_nutrition.csv",
        measure_conversion_path: Path | str = "data/raw/nutrition/cnf_2026/measure_weight_conversion.csv",
        measure_name_path: Path | str = "data/raw/nutrition/cnf_2026/measure_name.csv",
        cooked_rules_path: Path | str = "data/mappings/cooked_state_conversion_rules.csv",
        quality_checked_path: Path | str = "data/processed/recipe_ingredients_quality_checked.csv",
        raw_nutrient_path: Path | str = "data/raw/nutrition/cnf_2026/nutrient_amount.csv",
        enable_state_yield: bool = False,
        enable_qualitative_estimates: bool = False,
    ) -> None:
        self.recipes_path = Path(recipes_path)
        self.linked_ingredients_path = Path(linked_ingredients_path)
        self.curated_mapping_path = Path(curated_mapping_path)
        self.cooked_rules_path = Path(cooked_rules_path)
        self.quality_checked_path = Path(quality_checked_path)
        self.raw_nutrient_path = Path(raw_nutrient_path)
        self.enable_state_yield = enable_state_yield
        self.enable_qualitative_estimates = enable_qualitative_estimates

        # Load cooked state conversion rules
        self._cooked_rules: Dict[Tuple[str, str], Optional[float]] = {}
        if self.cooked_rules_path.is_file():
            df_cr = pd.read_csv(self.cooked_rules_path)
            for _, row in df_cr.iterrows():
                cname = str(row["canonical_name"]).lower().strip()
                sstate = str(row["source_state"]).lower().strip()
                cf = row.get("conversion_factor")
                try:
                    factor = float(cf) if pd.notna(cf) and str(cf).strip() != "" else None
                except (ValueError, TypeError):
                    factor = None
                self._cooked_rules[(cname, sstate)] = factor

        # Load curated mapping to identify active CNF food codes
        curated_df = pd.read_csv(self.curated_mapping_path)
        active_codes: Set[int] = set(
            curated_df["cnf_food_code"].dropna().astype(int).unique()
        )

        # Initialize converter and nutrient lookup
        self.converter = MeasureConverter(
            conversion_path=measure_conversion_path,
            measure_name_path=measure_name_path,
        )
        self.lookup = NutrientLookup(
            cnf_nutrition_path=cnf_nutrition_path,
            raw_nutrient_path=raw_nutrient_path,
            active_food_codes=active_codes,
        )

        # Store curated mapping dictionary for fast lookup
        self._curated_map: Dict[str, Dict[str, any]] = {}
        for _, row in curated_df.iterrows():
            iid = str(row["ingredient_id"]).strip()
            fc = int(row["cnf_food_code"]) if pd.notna(row["cnf_food_code"]) else None
            self._curated_map[iid] = {
                "curation_status": str(row["curation_status"]).strip(),
                "cnf_food_code": fc,
                "cnf_food_name": str(row["cnf_food_name"]).strip()
                if pd.notna(row["cnf_food_name"])
                else None,
            }

    def process_all(
        self,
        enable_state_yield: Optional[bool] = None,
        enable_qualitative_estimates: Optional[bool] = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Execute the complete nutrition calculation pipeline across all recipes."""
        if enable_state_yield is not None:
            self.enable_state_yield = enable_state_yield
        if enable_qualitative_estimates is not None:
            self.enable_qualitative_estimates = enable_qualitative_estimates
        recipes_df = pd.read_csv(self.recipes_path)

        # Use quality-checked representation when available, else fallback to linked ingredients
        if self.quality_checked_path.is_file():
            ril_df = pd.read_csv(self.quality_checked_path)
        else:
            ril_df = pd.read_csv(self.linked_ingredients_path)

        # 1. Process ingredient-level rows
        ingredient_rows: List[Dict[str, any]] = []
        recipe_ingredient_map: Dict[str, List[Dict[str, any]]] = {}

        for _, row in ril_df.iterrows():
            calc_row = self._process_ingredient_row(row)
            ingredient_rows.append(calc_row)

            rid = calc_row["recipe_id"]
            if rid not in recipe_ingredient_map:
                recipe_ingredient_map[rid] = []
            recipe_ingredient_map[rid].append(calc_row)

        ingredient_nutrition_df = pd.DataFrame(
            ingredient_rows, columns=INGREDIENT_NUTRITION_COLUMNS
        )

        # 2. Aggregate recipe-level rows
        recipe_rows: List[Dict[str, any]] = []
        for _, rrow in recipes_df.iterrows():
            rid = str(rrow["recipe_id"]).strip()
            rname = str(rrow["recipe_name"]).strip() if pd.notna(rrow["recipe_name"]) else ""
            servings_raw = rrow.get("servings")

            items = recipe_ingredient_map.get(rid, [])
            rec_calc = self._aggregate_recipe(rid, rname, servings_raw, items)
            recipe_rows.append(rec_calc)

        recipe_nutrition_df = pd.DataFrame(recipe_rows, columns=RECIPE_NUTRITION_COLUMNS)

        return ingredient_nutrition_df, recipe_nutrition_df

    def _process_ingredient_row(self, row: pd.Series | Dict[str, any]) -> Dict[str, any]:
        """Process a single recipe ingredient row deterministically."""
        recipe_id = str(row["recipe_id"]).strip()
        orig_ing = str(row["original_ingredient"]) if pd.notna(row.get("original_ingredient")) else ""
        ing = str(row["ingredient"]) if pd.notna(row.get("ingredient")) else ""
        raw_qty = row.get("original_quantity", row.get("quantity"))
        raw_unit = row.get("original_unit", row.get("unit"))
        prep = str(row["preparation"]) if pd.notna(row.get("preparation")) else ""
        iid = str(row["ingredient_id"]).strip() if pd.notna(row.get("ingredient_id")) else None
        canon = str(row["canonical_ingredient"]).strip() if pd.notna(row.get("canonical_ingredient")) else None
        link_status = str(row["mapping_status"]).strip() if pd.notna(row.get("mapping_status")) else "REVIEW"

        # Check for quality-checked effective values
        quality_status = str(row.get("quality_status", "ORIGINAL")).strip()
        is_unit_corrected = (quality_status == "CORRECTED_SOURCE_UNIT")
        eff_qty = row.get("effective_quantity", raw_qty)
        eff_unit = row.get("effective_unit", raw_unit)

        calc_qty = eff_qty if is_unit_corrected else raw_qty
        calc_unit = eff_unit if is_unit_corrected else raw_unit

        # Quantity parsing and unit normalization
        qres = parse_quantity(calc_qty)
        norm_unit = normalize_unit(calc_unit)

        # Mapping quality and curated CNF info
        if link_status == "REVIEW" or iid is None:
            mapping_quality = "UNMAPPED"
            curation_status = None
            cnf_food_code = None
            cnf_food_name = None
        else:
            cur_info = self._curated_map.get(iid, {})
            curation_status = cur_info.get("curation_status", "NO_MATCH")
            cnf_food_code = cur_info.get("cnf_food_code")
            cnf_food_name = cur_info.get("cnf_food_name")
            mapping_quality = curation_status

        # Water check
        is_water = bool(canon == "water" or iid == "ING00126")

        # State mismatch detection (cooked text cue with raw/dry CNF food)
        combined_text = f"{orig_ing} {ing} {prep}".lower()
        cooked_match = COOKED_STATE_CUES.search(combined_text)
        has_cooked_cue = bool(cooked_match)
        is_cnf_dry_raw = bool(cnf_food_name and DRY_RAW_CNF_CUES.search(cnf_food_name))

        state_status = "MATCHED"
        applied_yield_factor = None
        source_state_cue = None

        if is_cnf_dry_raw and has_cooked_cue and mapping_quality in ("APPROVED", "NEEDS_REVIEW") and not is_water:
            state_cue = cooked_match.group(1).lower()
            source_state_cue = state_cue
            canon_clean = canon.lower().strip() if canon else ""
            if state_cue == "soaked":
                # SOAKED must NOT be treated as cooked, nor fallback to cooked
                if self.enable_state_yield and (canon_clean, "soaked") in self._cooked_rules and self._cooked_rules[(canon_clean, "soaked")] is not None:
                    applied_yield_factor = self._cooked_rules[(canon_clean, "soaked")]
                    state_status = "SOAKING_YIELD_ESTIMATE"
                else:
                    state_status = "STATE_REVIEW_REQUIRED"
            else:
                if self.enable_state_yield and (canon_clean, state_cue) in self._cooked_rules and self._cooked_rules[(canon_clean, state_cue)] is not None:
                    applied_yield_factor = self._cooked_rules[(canon_clean, state_cue)]
                    state_status = "COOKING_YIELD_CONVERSION"
                elif self.enable_state_yield and (canon_clean, "cooked") in self._cooked_rules and self._cooked_rules[(canon_clean, "cooked")] is not None:
                    applied_yield_factor = self._cooked_rules[(canon_clean, "cooked")]
                    state_status = "COOKING_YIELD_CONVERSION"
                else:
                    state_status = "STATE_MISMATCH"

        # Measure conversion
        if state_status in ("STATE_MISMATCH", "STATE_REVIEW_REQUIRED"):
            conversion_status = state_status
            grams = None
            if state_status == "STATE_REVIEW_REQUIRED":
                calc_notes = (
                    f"[STATUS: UNAVAILABLE] [METHOD: NONE] [PROVENANCE: STATE_REVIEW_REQUIRED] [CONFIDENCE: UNAVAILABLE] "
                    f"Soaked state detected for '{canon_clean}' without established soaking yield factor; "
                    f"nutrition calculation withheld pending culinary review"
                )
            else:
                calc_notes = (
                    "[STATUS: STATE_MISMATCH] [METHOD: NONE] [PROVENANCE: NONE] [CONFIDENCE: UNAVAILABLE] "
                    "State mismatch: recipe specifies cooked/prepared state but CNF food is raw/dry; "
                    "nutrition calculation withheld pending cooking-yield model"
                )
        else:
            cres = self.converter.convert(
                food_code=cnf_food_code,
                quantity=qres.parsed_quantity,
                normalized_unit=norm_unit,
                original_ingredient=orig_ing,
                preparation=prep,
                is_water=is_water,
                mapping_quality=mapping_quality,
                canonical_ingredient=canon,
                estimate_qualitative=self.enable_qualitative_estimates,
            )
            conversion_status = cres.conversion_status
            grams = cres.grams
            calc_notes = cres.notes

            if state_status == "COOKING_YIELD_CONVERSION" and applied_yield_factor is not None and grams is not None:
                raw_eq_grams = round(grams * applied_yield_factor, 3)
                calc_notes = (
                    f"[STATUS: ESTIMATED] [METHOD: COOKING_YIELD_CONVERSION] [PROVENANCE: CNF_2026_YIELD] [CONFIDENCE: MEDIUM] "
                    f"Converted {grams:.1f}g {source_state_cue} mass to raw dry equivalent ({raw_eq_grams:.1f}g) "
                    f"using yield factor {applied_yield_factor} (USDA Table of Cooking Yields)"
                )
                grams = raw_eq_grams
                conversion_status = "COOKING_YIELD_CONVERSION"
            elif state_status == "SOAKING_YIELD_ESTIMATE" and applied_yield_factor is not None and grams is not None:
                raw_eq_grams = round(grams * applied_yield_factor, 3)
                calc_notes = (
                    f"[STATUS: ESTIMATED] [METHOD: SOAKING_YIELD_ESTIMATE] [PROVENANCE: SOAKING_YIELD_ESTIMATE] [CONFIDENCE: MEDIUM] "
                    f"Converted {grams:.1f}g soaked mass to raw dry equivalent ({raw_eq_grams:.1f}g) "
                    f"using soaking yield factor {applied_yield_factor} (USDA Cooking and Soaking Factors)"
                )
                grams = raw_eq_grams
                conversion_status = "SOAKING_YIELD_ESTIMATE"

        # Calculate nutrients
        if is_water:
            nut_prof = NutrientProfile()
            mapping_quality = "APPROVED"
            nutrition_quality = "EXACT"
            nutrition_source = "WATER_DEFAULT"
            calc_notes = "[STATUS: EXACT] [METHOD: ZERO_CALORIE_DEFAULT] [PROVENANCE: WATER_DEFAULT] [CONFIDENCE: HIGH] Water; zero nutritional contribution"
        elif is_unit_corrected:
            conversion_status = "SOURCE_UNIT_CORRECTION"
            if cnf_food_code is not None and grams is not None and grams > 0:
                nut_prof = self.lookup.calculate_nutrients(cnf_food_code, grams, is_water=False)
                nutrition_quality = "APPROXIMATE"
                nutrition_source = "QUALITY_CORRECTED"
                calc_notes = (
                    f"[STATUS: APPROXIMATE] [METHOD: SOURCE_UNIT_CORRECTION] [PROVENANCE: QUALITY_CORRECTED] "
                    f"[CONFIDENCE: HIGH] Corrected source unit prefix anomaly from {raw_qty} {raw_unit} to {eff_qty} {eff_unit}; "
                    f"converted mass {grams:.1f}g via {cres.conversion_status}"
                )
            else:
                nut_prof = NutrientProfile()
                nutrition_quality = "UNAVAILABLE"
                nutrition_source = "QUALITY_CORRECTED"
                calc_notes = (
                    f"[STATUS: UNAVAILABLE] [METHOD: SOURCE_UNIT_CORRECTION] [PROVENANCE: QUALITY_CORRECTED] "
                    f"[CONFIDENCE: HIGH] Corrected source unit prefix anomaly from {raw_qty} {raw_unit} to {eff_qty} {eff_unit}; "
                    f"food unmapped in CNF"
                )
        elif conversion_status == "ZERO_CALORIE_QUALITATIVE":
            nut_prof = NutrientProfile()
            nutrition_quality = "EXACT"
            nutrition_source = "QUALITATIVE_DEFAULT"
            calc_notes = f"[STATUS: EXACT] [METHOD: ZERO_CALORIE_DEFAULT] [PROVENANCE: QUALITATIVE_DEFAULT] [CONFIDENCE: HIGH] {calc_notes}"
        elif conversion_status == "ESTIMATED_QUALITATIVE" and grams is not None and grams > 0:
            nut_prof = self.lookup.calculate_nutrients(cnf_food_code, grams, is_water=False)
            nutrition_quality = "APPROXIMATE"
            nutrition_source = "ESTIMATED_QUALITATIVE"
            calc_notes = f"[STATUS: ESTIMATED] [METHOD: ESTIMATED_QUALITATIVE] [PROVENANCE: ESTIMATED_QUALITATIVE] [CONFIDENCE: MEDIUM] {calc_notes}"
        elif conversion_status in ("DIRECT_MASS", "CNF_MEASURE", "COOKING_YIELD_CONVERSION", "SOAKING_YIELD_ESTIMATE") and grams is not None and grams > 0:
            nut_prof = self.lookup.calculate_nutrients(cnf_food_code, grams, is_water=False)
            if conversion_status == "SOAKING_YIELD_ESTIMATE":
                nutrition_quality = "APPROXIMATE"
                nutrition_source = "SOAKING_YIELD_ESTIMATE"
            elif conversion_status == "COOKING_YIELD_CONVERSION":
                nutrition_quality = "APPROXIMATE"
                nutrition_source = "CNF_2026_YIELD"
            else:
                nutrition_quality = "APPROXIMATE" if mapping_quality == "NEEDS_REVIEW" else "EXACT"
                nutrition_source = "CNF_2026"
            if not str(calc_notes).startswith("[STATUS:"):
                calc_status = "APPROXIMATE" if nutrition_quality == "APPROXIMATE" else "EXACT"
                calc_notes = f"[STATUS: {calc_status}] [METHOD: {conversion_status}] [PROVENANCE: {nutrition_source}] [CONFIDENCE: HIGH] {calc_notes}"
        else:
            nut_prof = NutrientProfile()
            nutrition_quality = "UNAVAILABLE"
            nutrition_source = "NONE"
            if not str(calc_notes).startswith("[STATUS:"):
                calc_notes = f"[STATUS: UNAVAILABLE] [METHOD: NONE] [PROVENANCE: NONE] [CONFIDENCE: UNAVAILABLE] {calc_notes}"

        return {
            "recipe_id": recipe_id,
            "original_ingredient": orig_ing,
            "ingredient": ing,
            "quantity": raw_qty,
            "unit": raw_unit,
            "preparation": prep,
            "ingredient_id": iid,
            "canonical_ingredient": canon,
            "mapping_status": link_status,
            "curation_status": curation_status,
            "cnf_food_code": cnf_food_code,
            "cnf_food_name": cnf_food_name,
            "parsed_quantity": qres.parsed_quantity,
            "quantity_parse_status": qres.parse_status,
            "normalized_unit": norm_unit,
            "grams": grams,
            "conversion_status": conversion_status,
            "state_status": state_status,
            "energy_kcal": nut_prof.energy_kcal,
            "protein_g": nut_prof.protein_g,
            "fat_g": nut_prof.fat_g,
            "carbs_g": nut_prof.carbs_g,
            "fiber_g": nut_prof.fiber_g,
            "sugar_g": nut_prof.sugar_g,
            "sodium_mg": nut_prof.sodium_mg,
            "mapping_quality": mapping_quality,
            "nutrition_quality": nutrition_quality,
            "nutrition_source": nutrition_source,
            "calculation_notes": calc_notes,
        }

    def _aggregate_recipe(
        self,
        recipe_id: str,
        recipe_name: str,
        servings_raw: any,
        ingredients: List[Dict[str, any]],
    ) -> Dict[str, any]:
        """Aggregate calculated ingredient nutrients into recipe totals and per-serving amounts."""
        # Servings parsing
        try:
            servings_val = float(servings_raw) if pd.notna(servings_raw) else None
            if servings_val is not None and servings_val <= 0:
                servings_val = None
        except (ValueError, TypeError):
            servings_val = None

        ingredient_count = len(ingredients)
        calculated_count = 0
        unmapped_count = 0
        no_match_count = 0
        needs_review_count = 0
        qualitative_count = 0
        conversion_failure_count = 0
        state_mismatch_count = 0

        tot_energy = 0.0
        tot_protein = 0.0
        tot_fat = 0.0
        tot_carbs = 0.0
        tot_fiber = 0.0
        tot_sugar = 0.0
        tot_sodium = 0.0

        for item in ingredients:
            is_water = bool(
                item["canonical_ingredient"] == "water" or item["ingredient_id"] == "ING00126"
            )

            # Categorize counters
            if item["mapping_quality"] == "UNMAPPED":
                unmapped_count += 1
            elif item["mapping_quality"] == "NO_MATCH":
                no_match_count += 1
            elif item["mapping_quality"] == "NEEDS_REVIEW":
                needs_review_count += 1

            if item["conversion_status"] in (
                "QUALITATIVE_QUANTITY",
                "ZERO_CALORIE_QUALITATIVE",
                "ESTIMATED_QUALITATIVE",
            ):
                qualitative_count += 1
            elif item["conversion_status"] in (
                "NO_CNF_CONVERSION",
                "NEEDS_PROXY",
                "MISSING_QUANTITY",
            ):
                conversion_failure_count += 1
            elif item["conversion_status"] in ("STATE_MISMATCH", "STATE_REVIEW_REQUIRED") or item["state_status"] in ("STATE_MISMATCH", "STATE_REVIEW_REQUIRED"):
                state_mismatch_count += 1

            if item["nutrition_quality"] in ("EXACT", "APPROXIMATE"):
                calculated_count += 1
                tot_energy += item["energy_kcal"]
                tot_protein += item["protein_g"]
                tot_fat += item["fat_g"]
                tot_carbs += item["carbs_g"]
                tot_fiber += item["fiber_g"]
                tot_sugar += item["sugar_g"]
                tot_sodium += item["sodium_mg"]

        # Recipe nutrition quality determination
        if ingredient_count == 0:
            rec_quality = "PARTIAL"
        else:
            # Check non-water ingredients for any missing nutrition contribution
            non_water_items = [
                it
                for it in ingredients
                if not (it["canonical_ingredient"] == "water" or it["ingredient_id"] == "ING00126")
            ]
            has_unavailable = any(it["nutrition_quality"] == "UNAVAILABLE" for it in non_water_items)
            has_approximate = any(it["nutrition_quality"] == "APPROXIMATE" for it in non_water_items)

            if has_unavailable:
                rec_quality = "PARTIAL"
            elif has_approximate:
                rec_quality = "APPROXIMATE"
            else:
                rec_quality = "COMPLETE"

        # Round totals
        tot_energy = round(tot_energy, 3)
        tot_protein = round(tot_protein, 3)
        tot_fat = round(tot_fat, 3)
        tot_carbs = round(tot_carbs, 3)
        tot_fiber = round(tot_fiber, 3)
        tot_sugar = round(tot_sugar, 3)
        tot_sodium = round(tot_sodium, 3)

        # Per serving calculation
        if servings_val is not None and servings_val > 0:
            per_energy = round(tot_energy / servings_val, 3)
            per_protein = round(tot_protein / servings_val, 3)
            per_fat = round(tot_fat / servings_val, 3)
            per_carbs = round(tot_carbs / servings_val, 3)
            per_fiber = round(tot_fiber / servings_val, 3)
            per_sugar = round(tot_sugar / servings_val, 3)
            per_sodium = round(tot_sodium / servings_val, 3)
        else:
            per_energy = None
            per_protein = None
            per_fat = None
            per_carbs = None
            per_fiber = None
            per_sugar = None
            per_sodium = None

        return {
            "recipe_id": recipe_id,
            "recipe_name": recipe_name,
            "servings": servings_raw,
            "total_calories_kcal": tot_energy,
            "total_protein_g": tot_protein,
            "total_fat_g": tot_fat,
            "total_carbs_g": tot_carbs,
            "total_fiber_g": tot_fiber,
            "total_sugar_g": tot_sugar,
            "total_sodium_mg": tot_sodium,
            "per_serving_calories_kcal": per_energy,
            "per_serving_protein_g": per_protein,
            "per_serving_fat_g": per_fat,
            "per_serving_carbs_g": per_carbs,
            "per_serving_fiber_g": per_fiber,
            "per_serving_sugar_g": per_sugar,
            "per_serving_sodium_mg": per_sodium,
            "nutrition_quality": rec_quality,
            "ingredient_count": ingredient_count,
            "calculated_ingredient_count": calculated_count,
            "unmapped_ingredient_count": unmapped_count,
            "no_match_ingredient_count": no_match_count,
            "needs_review_ingredient_count": needs_review_count,
            "qualitative_quantity_count": qualitative_count,
            "conversion_failure_count": conversion_failure_count,
            "state_mismatch_count": state_mismatch_count,
        }

    def save_outputs(
        self,
        ingredient_df: pd.DataFrame,
        recipe_df: pd.DataFrame,
        ingredient_out_path: Path | str = "data/processed/recipe_ingredient_nutrition.csv",
        recipe_out_path: Path | str = "data/processed/recipe_nutrition.csv",
    ) -> None:
        """Write calculation output datasets to disk."""
        ing_path = Path(ingredient_out_path)
        rec_path = Path(recipe_out_path)

        ing_path.parent.mkdir(parents=True, exist_ok=True)
        rec_path.parent.mkdir(parents=True, exist_ok=True)

        ingredient_df.to_csv(ing_path, index=False)
        recipe_df.to_csv(rec_path, index=False)


def run_nutrition_engine(
    enable_state_yield: bool = True,
    enable_qualitative_estimates: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Execute the full nutrition calculation engine and save artifacts."""
    engine = RecipeNutritionEngine(
        enable_state_yield=enable_state_yield,
        enable_qualitative_estimates=enable_qualitative_estimates,
    )
    ing_df, rec_df = engine.process_all(
        enable_state_yield=enable_state_yield,
        enable_qualitative_estimates=enable_qualitative_estimates,
    )
    engine.save_outputs(ing_df, rec_df)
    return ing_df, rec_df


if __name__ == "__main__":
    import time

    t0 = time.time()
    print("Running KitchenPilot-V1 Recipe Nutrition Engine...")
    ing_df, rec_df = run_nutrition_engine()
    print(f"Completed in {time.time() - t0:.2f}s")
    print(f"Processed {len(ing_df):,} ingredient rows across {len(rec_df):,} recipes.")
    print("Recipe quality breakdown:")
    print(rec_df["nutrition_quality"].value_counts())
