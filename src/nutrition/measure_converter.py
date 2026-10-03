"""Food-specific measure conversion using Canadian Nutrient File (CNF) 2026 data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class ConversionResult:
    """Structured result of converting a quantity and unit into grams."""

    grams: Optional[float]
    conversion_status: str
    notes: Optional[str] = None


QUALITATIVE_REGEX = re.compile(
    r"\b(to\s+taste|as\s+per\s+taste|as\s+required|as\s+needed|for\s+cooking|for\s+frying|pinch|pinches|handful|handfuls)\b",
    re.IGNORECASE,
)


class MeasureConverter:
    """Deterministic, food-specific measure converter backed by CNF conversion tables."""

    def __init__(
        self,
        conversion_path: Path | str = "data/raw/nutrition/cnf_2026/measure_weight_conversion.csv",
        measure_name_path: Path | str = "data/raw/nutrition/cnf_2026/measure_name.csv",
        item_defaults_path: Path | str = "data/mappings/culinary_item_mass_defaults.csv",
        qualitative_rules_path: Path | str = "data/mappings/qualitative_quantity_rules.csv",
        measure_overrides_path: Path | str = "data/mappings/ingredient_measure_overrides.csv",
    ) -> None:
        self.conversion_path = Path(conversion_path)
        self.measure_name_path = Path(measure_name_path)
        self.item_defaults_path = Path(item_defaults_path)
        self.qualitative_rules_path = Path(qualitative_rules_path)
        self.measure_overrides_path = Path(measure_overrides_path)
        self._food_measures: Dict[int, List[Tuple[int, str, float]]] = {}
        self._item_mass_defaults: Dict[str, float] = {}
        self._qualitative_rules: Dict[str, Dict[str, any]] = {}
        self._measure_overrides: Dict[Tuple[str, str], Dict[str, any]] = {}
        self._load_tables()
        self._load_calibration_tables()

    def _load_calibration_tables(self) -> None:
        """Load item mass defaults, qualitative quantity rules, and measure overrides."""
        if self.item_defaults_path.is_file():
            df_items = pd.read_csv(self.item_defaults_path)
            for _, row in df_items.iterrows():
                cname = str(row["canonical_name"]).lower().strip()
                mass = float(row["default_mass_g"])
                self._item_mass_defaults[cname] = mass

        if self.qualitative_rules_path.is_file():
            df_qual = pd.read_csv(self.qualitative_rules_path)
            for _, row in df_qual.iterrows():
                pat = str(row["ingredient_pattern"]).lower().strip()
                self._qualitative_rules[pat] = {
                    "classification": str(row["classification"]).strip(),
                    "default_quantity": float(row["default_quantity"]) if pd.notna(row["default_quantity"]) else None,
                    "default_unit": str(row["default_unit"]).strip() if pd.notna(row["default_unit"]) else None,
                    "basis": str(row["basis"]) if pd.notna(row["basis"]) else "",
                    "notes": str(row["notes"]) if pd.notna(row["notes"]) else "",
                }

        if self.measure_overrides_path.is_file():
            df_ov = pd.read_csv(self.measure_overrides_path)
            for _, row in df_ov.iterrows():
                enabled = row.get("enabled", True)
                if enabled in (True, "True", "true", 1, "1"):
                    cname = str(row.get("canonical_ingredient") if pd.notna(row.get("canonical_ingredient")) else row.get("canonical_name", "")).lower().strip()
                    unit = str(row["unit"]).lower().strip()
                    self._measure_overrides[(cname, unit)] = {
                        "grams_per_unit": float(row["grams_per_unit"]),
                        "source": str(row["source"]).strip(),
                        "confidence": str(row.get("confidence", "HIGH")).strip(),
                        "reason": str(row["reason"]).strip() if pd.notna(row.get("reason")) else "",
                    }

    def _load_tables(self) -> None:
        """Load and index user-defined CNF measure conversions by Food_Code."""
        if not self.conversion_path.is_file():
            raise FileNotFoundError(f"Missing conversion file: {self.conversion_path}")
        if not self.measure_name_path.is_file():
            raise FileNotFoundError(f"Missing measure name file: {self.measure_name_path}")

        conv_df = pd.read_csv(self.conversion_path)
        mname_df = pd.read_csv(self.measure_name_path)

        # Measure_Type_Code == 6 represents user-defined household & serving measures
        user_conv = conv_df[conv_df["Measure_Type_Code"] == 6].merge(
            mname_df, on="Measure_Code", how="left"
        )

        for _, row in user_conv.iterrows():
            fc = int(row["Food_Code"])
            mcode = int(row["Measure_Code"])
            mdesc = str(row["Measure_Description_and_Unit_EN"]).strip()
            weight = float(row["Measure_Weight_Conversion"])

            if fc not in self._food_measures:
                self._food_measures[fc] = []
            self._food_measures[fc].append((mcode, mdesc, weight))

    def convert(
        self,
        food_code: Optional[int],
        quantity: Optional[float],
        normalized_unit: Optional[str],
        original_ingredient: str = "",
        preparation: str = "",
        is_water: bool = False,
        mapping_quality: str = "APPROVED",
        canonical_ingredient: Optional[str] = None,
        estimate_qualitative: bool = False,
    ) -> ConversionResult:
        """Convert a recipe quantity and normalized unit into grams for a given food code."""
        # 1. Unmapped check
        if mapping_quality == "UNMAPPED":
            return ConversionResult(
                grams=None,
                conversion_status="UNMAPPED",
                notes="Ingredient has no canonical mapping",
            )

        # 2. NO_MATCH check
        if mapping_quality == "NO_MATCH":
            return ConversionResult(
                grams=None,
                conversion_status="NO_MATCH",
                notes="Canonical ingredient has no CNF match",
            )

        # 3. Water check
        if is_water:
            water_grams = self._estimate_water_grams(quantity, normalized_unit)
            return ConversionResult(
                grams=water_grams,
                conversion_status="WATER",
                notes="Water; zero nutritional contribution",
            )

        # 4. Check for qualitative quantity keywords
        if QUALITATIVE_REGEX.search(original_ingredient) or QUALITATIVE_REGEX.search(preparation):
            if estimate_qualitative:
                qual_res = self._handle_qualitative_quantity(
                    food_code=food_code,
                    canonical_ingredient=canonical_ingredient,
                    original_ingredient=original_ingredient,
                    preparation=preparation,
                )
                if qual_res is not None:
                    return qual_res
            return ConversionResult(
                grams=None,
                conversion_status="QUALITATIVE_QUANTITY",
                notes="Qualitative quantity (to taste / as required / pinch / handful)",
            )

        # 5. Missing quantity check
        if quantity is None:
            return ConversionResult(
                grams=None,
                conversion_status="MISSING_QUANTITY",
                notes="Missing or unparseable quantity",
            )

        # 6. Special units requiring proxies
        if normalized_unit == "inch":
            if canonical_ingredient:
                canon_clean = canonical_ingredient.lower().strip()
                if (canon_clean, "inch") in self._measure_overrides:
                    ov = self._measure_overrides[(canon_clean, "inch")]
                    grams = round(quantity * ov["grams_per_unit"], 3)
                    return ConversionResult(
                        grams=grams,
                        conversion_status="CNF_MEASURE",
                        notes=f"Ingredient-specific dimension conversion ({ov['grams_per_unit']}g/inch, {ov['source']})",
                    )
            return ConversionResult(
                grams=None,
                conversion_status="NEEDS_PROXY",
                notes="Linear dimension (inch) requires proxy conversion",
            )
        if normalized_unit in ("sprig", "bunch"):
            return ConversionResult(
                grams=None,
                conversion_status="NEEDS_PROXY",
                notes=f"Botanical count unit ({normalized_unit}) requires proxy conversion",
            )

        # 7. Mass conversion (Direct metric mass)
        if normalized_unit == "g":
            return ConversionResult(
                grams=float(quantity),
                conversion_status="DIRECT_MASS",
                notes="Direct metric mass (grams)",
            )
        if normalized_unit == "kg":
            return ConversionResult(
                grams=float(quantity) * 1000.0,
                conversion_status="DIRECT_MASS",
                notes="Direct metric mass (kg -> grams)",
            )

        # 8. Must have a valid CNF food code for household/volume/discrete measure conversions
        if food_code is None:
            return ConversionResult(
                grams=None,
                conversion_status="NO_CNF_CONVERSION",
                notes="No CNF food code available for measure conversion",
            )

        canon_clean = canonical_ingredient.lower().strip() if canonical_ingredient else ""

        measures = self._food_measures.get(int(food_code), [])
        if not measures:
            if canon_clean and (canon_clean, normalized_unit) in self._measure_overrides:
                ov = self._measure_overrides[(canon_clean, normalized_unit)]
                grams = round(quantity * ov["grams_per_unit"], 3)
                return ConversionResult(
                    grams=grams,
                    conversion_status="CNF_MEASURE",
                    notes=f"Ingredient measure override ({ov['grams_per_unit']}g/{normalized_unit}, {ov['source']})",
                )
            if normalized_unit in ("piece", None) and canon_clean:
                if canon_clean in self._item_mass_defaults:
                    default_mass = self._item_mass_defaults[canon_clean]
                    grams = round(quantity * default_mass, 3)
                    return ConversionResult(
                        grams=grams,
                        conversion_status="CNF_MEASURE",
                        notes=f"Culinary item mass calibration ({default_mass}g/unit)",
                    )
            return ConversionResult(
                grams=None,
                conversion_status="NO_CNF_CONVERSION",
                notes=f"No user-defined CNF measures available for Food_Code {food_code}",
            )

        # 9. Volume conversions: cup, tbsp, tsp, ml, liter
        res = None
        if normalized_unit == "cup":
            res = self._convert_cup(measures, quantity)
        elif normalized_unit == "tbsp":
            res = self._convert_tbsp(measures, quantity)
        elif normalized_unit == "tsp":
            res = self._convert_tsp(measures, quantity)
        elif normalized_unit == "ml":
            res = self._convert_ml(measures, quantity)
        elif normalized_unit == "liter":
            res = self._convert_liter(measures, quantity)
        elif normalized_unit == "clove":
            res = self._convert_clove(measures, quantity)
        elif normalized_unit in ("piece", None):
            res = self._convert_discrete_item(
                measures,
                quantity,
                canonical_ingredient=canonical_ingredient,
                original_ingredient=original_ingredient,
            )

        if res is not None:
            if res.conversion_status == "CNF_MEASURE":
                return res
            # Fallback to measure override if available
            if canon_clean and (canon_clean, normalized_unit) in self._measure_overrides:
                ov = self._measure_overrides[(canon_clean, normalized_unit)]
                grams = round(quantity * ov["grams_per_unit"], 3)
                return ConversionResult(
                    grams=grams,
                    conversion_status="CNF_MEASURE",
                    notes=f"Ingredient measure override ({ov['grams_per_unit']}g/{normalized_unit}, {ov['source']})",
                )
            return res

        # Fallback to measure override for any unhandled unit
        if canon_clean and (canon_clean, normalized_unit) in self._measure_overrides:
            ov = self._measure_overrides[(canon_clean, normalized_unit)]
            grams = round(quantity * ov["grams_per_unit"], 3)
            return ConversionResult(
                grams=grams,
                conversion_status="CNF_MEASURE",
                notes=f"Ingredient measure override ({ov['grams_per_unit']}g/{normalized_unit}, {ov['source']})",
            )

        return ConversionResult(
            grams=None,
            conversion_status="NO_CNF_CONVERSION",
            notes=f"No matching CNF measure for unit '{normalized_unit}'",
        )

    def _convert_cup(
        self, measures: List[Tuple[int, str, float]], quantity: float
    ) -> ConversionResult:
        """Convert cup measurement using 250ml CNF measures with priority."""
        # 1. Exact 250 ml match
        exact_250 = [m for m in measures if re.match(r"^250\s*ml$", m[1], re.IGNORECASE)]
        if exact_250:
            grams = quantity * exact_250[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"Exact CNF measure: '{exact_250[0][1]}'",
            )

        # 2. Prepared 250 ml (chopped, diced, sliced, etc.)
        prep_250 = [m for m in measures if re.search(r"\b250\s*ml\b", m[1], re.IGNORECASE)]
        if prep_250:
            grams = quantity * prep_250[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"CNF prepared measure: '{prep_250[0][1]}'",
            )

        # 3. Scaled metric volume equivalents (125ml * 2, 100ml * 2.5, 500ml * 0.5)
        for m in measures:
            if re.search(r"\b125\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] * 2.0)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Scaled CNF measure (125ml x 2): '{m[1]}'",
                )
            if re.search(r"\b100\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] * 2.5)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Scaled CNF measure (100ml x 2.5): '{m[1]}'",
                )

        return ConversionResult(
            grams=None,
            conversion_status="NO_CNF_CONVERSION",
            notes="No 250ml, 125ml, or 100ml volume measure in CNF for food",
        )

    def _convert_tbsp(
        self, measures: List[Tuple[int, str, float]], quantity: float
    ) -> ConversionResult:
        """Convert tablespoon measurement using 15ml CNF measures with priority."""
        # 1. Exact 15 ml
        exact_15 = [m for m in measures if re.match(r"^15\s*ml$", m[1], re.IGNORECASE)]
        if exact_15:
            grams = quantity * exact_15[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"Exact CNF measure: '{exact_15[0][1]}'",
            )

        # 2. Prepared 15 ml
        prep_15 = [m for m in measures if re.search(r"\b15\s*ml\b", m[1], re.IGNORECASE)]
        if prep_15:
            grams = quantity * prep_15[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"CNF prepared measure: '{prep_15[0][1]}'",
            )

        # 3. Scaled volume equivalents (5ml * 3, 100ml * 0.15, 250ml * 0.06)
        for m in measures:
            if re.search(r"\b5\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] * 3.0)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Scaled CNF measure (5ml x 3): '{m[1]}'",
                )
            if re.search(r"\b100\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] * 0.15)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Scaled CNF measure (100ml x 0.15): '{m[1]}'",
                )
            if re.search(r"\b250\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] * 0.06)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Scaled CNF measure (250ml x 0.06): '{m[1]}'",
                )

        return ConversionResult(
            grams=None,
            conversion_status="NO_CNF_CONVERSION",
            notes="No 15ml, 5ml, or 100ml volume measure in CNF for food",
        )

    def _convert_tsp(
        self, measures: List[Tuple[int, str, float]], quantity: float
    ) -> ConversionResult:
        """Convert teaspoon measurement using 5ml CNF measures with priority."""
        # 1. Exact 5 ml
        exact_5 = [m for m in measures if re.match(r"^5\s*ml$", m[1], re.IGNORECASE)]
        if exact_5:
            grams = quantity * exact_5[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"Exact CNF measure: '{exact_5[0][1]}'",
            )

        # 2. Prepared 5 ml
        prep_5 = [m for m in measures if re.search(r"\b5\s*ml\b", m[1], re.IGNORECASE)]
        if prep_5:
            grams = quantity * prep_5[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"CNF prepared measure: '{prep_5[0][1]}'",
            )

        # 3. Scaled volume equivalents (15ml / 3, 100ml * 0.05, 250ml * 0.02)
        for m in measures:
            if re.search(r"\b15\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] / 3.0)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Scaled CNF measure (15ml / 3): '{m[1]}'",
                )
            if re.search(r"\b100\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] * 0.05)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Scaled CNF measure (100ml x 0.05): '{m[1]}'",
                )
            if re.search(r"\b250\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] * 0.02)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Scaled CNF measure (250ml x 0.02): '{m[1]}'",
                )

        return ConversionResult(
            grams=None,
            conversion_status="NO_CNF_CONVERSION",
            notes="No 5ml, 15ml, or 100ml volume measure in CNF for food",
        )

    def _convert_ml(
        self, measures: List[Tuple[int, str, float]], quantity: float
    ) -> ConversionResult:
        """Convert milliliters using food volume density."""
        for m in measures:
            if re.search(r"\b100\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] / 100.0)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Converted via CNF volume density (100ml): '{m[1]}'",
                )
            if re.search(r"\b250\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] / 250.0)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Converted via CNF volume density (250ml): '{m[1]}'",
                )
            if re.search(r"\b15\s*ml\b", m[1], re.IGNORECASE):
                grams = quantity * (m[2] / 15.0)
                return ConversionResult(
                    grams=round(grams, 3),
                    conversion_status="CNF_MEASURE",
                    notes=f"Converted via CNF volume density (15ml): '{m[1]}'",
                )

        return ConversionResult(
            grams=None,
            conversion_status="NO_CNF_CONVERSION",
            notes="No volume measure in CNF to determine density for ml conversion",
        )

    def _convert_liter(
        self, measures: List[Tuple[int, str, float]], quantity: float
    ) -> ConversionResult:
        """Convert liters using food volume density."""
        ml_res = self._convert_ml(measures, quantity * 1000.0)
        if ml_res.conversion_status == "CNF_MEASURE":
            return ConversionResult(
                grams=ml_res.grams,
                conversion_status="CNF_MEASURE",
                notes=f"Converted liters via CNF volume density: {ml_res.notes}",
            )
        return ml_res

    def _convert_clove(
        self, measures: List[Tuple[int, str, float]], quantity: float
    ) -> ConversionResult:
        """Convert clove measurement (e.g. garlic)."""
        cloves = [m for m in measures if re.search(r"\bclove\b", m[1], re.IGNORECASE)]
        if cloves:
            grams = quantity * cloves[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"Exact CNF clove measure: '{cloves[0][1]}'",
            )
        return ConversionResult(
            grams=None,
            conversion_status="NO_CNF_CONVERSION",
            notes="No CNF clove measure found for food",
        )

    def _convert_discrete_item(
        self,
        measures: List[Tuple[int, str, float]],
        quantity: float,
        canonical_ingredient: Optional[str] = None,
        original_ingredient: str = "",
    ) -> ConversionResult:
        """Convert discrete whole items (e.g. 1 onion, 2 eggs, 3 tomatoes)."""
        canon_clean = canonical_ingredient.lower().strip() if canonical_ingredient else ""
        orig_clean = original_ingredient.lower().strip() if original_ingredient else ""

        # Priority 0: Explicit culinary item mass calibration
        # Check black pepper / peppercorn specifically
        if canon_clean in ("black pepper", "peppercorn"):
            if re.search(r"\b(peppercorn|peppercorns|whole)\b", orig_clean) or canon_clean == "peppercorn":
                default_mass = self._item_mass_defaults.get(canon_clean, 0.05)
                grams = round(quantity * default_mass, 3)
                return ConversionResult(
                    grams=grams,
                    conversion_status="CNF_MEASURE",
                    notes=f"Culinary item mass calibration ({default_mass}g/peppercorn)",
                )
            else:
                # E.g. "4 Black pepper powder" with missing unit - do NOT assume peppercorn mass or 100 ml whole
                return ConversionResult(
                    grams=None,
                    conversion_status="NO_CNF_CONVERSION",
                    notes="Black pepper powder without unit cannot use discrete item conversion",
                )

        if canon_clean and canon_clean in self._item_mass_defaults:
            default_mass = self._item_mass_defaults[canon_clean]
            grams = round(quantity * default_mass, 3)
            return ConversionResult(
                grams=grams,
                conversion_status="CNF_MEASURE",
                notes=f"Culinary item mass calibration ({default_mass}g/unit)",
            )

        # Priority 1: Genuine CNF discrete item measure
        # Filter out ANY volumetric, container, packaging, or shredded/packed measures
        vol_container_re = re.compile(
            r"\b(\d+\s*ml|ml|l|liter|litres?|cup|cups|tbsp|tablespoon|tsp|teaspoon|fl\s*oz|can|jar|bag|package|packet|container|bottle|glass|tub|packed|box|carton)\b",
            re.IGNORECASE,
        )
        discrete_measures = [m for m in measures if not vol_container_re.search(m[1])]

        # Priority 1a: Medium whole / medium
        mediums = [m for m in discrete_measures if re.search(r"\bmedium\b", m[1], re.IGNORECASE)]
        if mediums:
            grams = quantity * mediums[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"CNF medium item measure: '{mediums[0][1]}'",
            )

        # Priority 1b: Whole / Fruit / Egg / Potato / Item
        wholes = [
            m
            for m in discrete_measures
            if re.search(
                r"\b(whole|fruit|potato|onion|egg|tomato|pepper|banana|apple|cucumber|carrot|lemon|stalk|item)\b",
                m[1],
                re.IGNORECASE,
            )
        ]
        if wholes:
            grams = quantity * wholes[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"CNF whole item measure: '{wholes[0][1]}'",
            )

        # Priority 1c: Large item
        larges = [m for m in discrete_measures if re.search(r"\blarge\b", m[1], re.IGNORECASE)]
        if larges:
            grams = quantity * larges[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"CNF large item measure: '{larges[0][1]}'",
            )

        # Priority 1d: Slice
        slices = [m for m in discrete_measures if re.search(r"\bslice\b", m[1], re.IGNORECASE)]
        if slices:
            grams = quantity * slices[0][2]
            return ConversionResult(
                grams=round(grams, 3),
                conversion_status="CNF_MEASURE",
                notes=f"CNF slice measure: '{slices[0][1]}'",
            )

        # Priority 2: Defensible ingredient-specific item conversion override
        if canon_clean and (canon_clean, "piece") in self._measure_overrides:
            ov = self._measure_overrides[(canon_clean, "piece")]
            grams = round(quantity * ov["grams_per_unit"], 3)
            return ConversionResult(
                grams=grams,
                conversion_status="CNF_MEASURE",
                notes=f"Ingredient measure override ({ov['grams_per_unit']}g/piece, {ov['source']})",
            )

        # Priority 3: Otherwise UNAVAILABLE / NEEDS_REVIEW
        return ConversionResult(
            grams=None,
            conversion_status="NO_CNF_CONVERSION",
            notes="No discrete item measure (medium/whole/item/slice) in CNF for food (volumetric/container measures excluded)",
        )

    def _estimate_water_grams(
        self, quantity: Optional[float], normalized_unit: Optional[str]
    ) -> Optional[float]:
        """Estimate mass of water for provenance tracking (density 1.0 g/ml)."""
        if quantity is None:
            return None
        if normalized_unit == "g":
            return quantity
        if normalized_unit == "kg":
            return quantity * 1000.0
        if normalized_unit == "cup":
            return quantity * 250.0
        if normalized_unit == "tbsp":
            return quantity * 15.0
        if normalized_unit == "tsp":
            return quantity * 5.0
        if normalized_unit == "ml":
            return quantity * 1.0
        if normalized_unit == "liter":
            return quantity * 1000.0
        return None

    def _handle_qualitative_quantity(
        self,
        food_code: Optional[int],
        canonical_ingredient: Optional[str],
        original_ingredient: str,
        preparation: str,
    ) -> Optional[ConversionResult]:
        """Classify and optionally estimate qualitative quantities using curated rules."""
        text_lower = f"{original_ingredient} {preparation}".lower()
        canon_clean = canonical_ingredient.lower().strip() if canonical_ingredient else ""

        # Find matching rule
        matched_rule = None
        for pattern, rule in self._qualitative_rules.items():
            if pattern == canon_clean or re.search(r"\b" + re.escape(pattern) + r"\b", text_lower):
                matched_rule = rule
                break

        if not matched_rule:
            return None

        classification = matched_rule["classification"]
        if classification == "ZERO_CALORIE_QUALITATIVE":
            return ConversionResult(
                grams=None,
                conversion_status="ZERO_CALORIE_QUALITATIVE",
                notes=f"Zero-calorie qualitative seasoning ({matched_rule.get('notes', 'no calorie impact')})",
            )

        if classification == "ESTIMABLE_QUALITATIVE" and food_code is not None:
            def_qty = float(matched_rule["default_quantity"]) if pd.notna(matched_rule["default_quantity"]) else 1.0
            def_unit = str(matched_rule["default_unit"]).strip().lower() if pd.notna(matched_rule["default_unit"]) else "tbsp"

            measures = self._food_measures.get(int(food_code), [])
            if def_unit == "tbsp":
                vol_res = self._convert_tbsp(measures, def_qty)
            elif def_unit == "tsp":
                vol_res = self._convert_tsp(measures, def_qty)
            else:
                vol_res = ConversionResult(grams=None, conversion_status="NO_CNF_CONVERSION")

            if vol_res.conversion_status == "CNF_MEASURE" and vol_res.grams is not None:
                return ConversionResult(
                    grams=vol_res.grams,
                    conversion_status="ESTIMATED_QUALITATIVE",
                    notes=f"Estimated qualitative fat: {def_qty} {def_unit} ({vol_res.grams}g) baseline ({matched_rule.get('basis', '')})",
                )

        if classification == "UNAVAILABLE_QUALITATIVE":
            return ConversionResult(
                grams=None,
                conversion_status="QUALITATIVE_QUANTITY",
                notes=f"Qualitative quantity withheld ({matched_rule.get('notes', 'no baseline')})",
            )

        return None

