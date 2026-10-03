"""Quantity parsing and unit normalization for the KitchenPilot nutrition engine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Optional


@dataclass(frozen=True)
class QuantityParseResult:
    """Structured representation of parsed quantity information."""

    parsed_quantity: Optional[float]
    parse_status: str
    original_quantity: str
    warning: Optional[str] = None


# Known unspaced fraction anomalies verified in the audit report
# data/mappings/nutrition_engine_data_audit.md
KNOWN_UNSPACED_FRACTION_ANOMALIES = {
    "11/2": 1.5,
    "21/2": 2.5,
    "11/4": 1.25,
}

# Unit normalization mappings
MASS_UNITS = {
    "gram": "g",
    "grams": "g",
    "g": "g",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
}

VOLUME_UNITS = {
    "cup": "cup",
    "cups": "cup",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tbsp": "tbsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tsp": "tsp",
    "ml": "ml",
    "liter": "liter",
    "liters": "liter",
    "l": "liter",
}

DISCRETE_UNITS = {
    "clove": "clove",
    "cloves": "clove",
    "piece": "piece",
    "pieces": "piece",
    "sprig": "sprig",
    "sprigs": "sprig",
    "bunch": "bunch",
    "inch": "inch",
    "inches": "inch",
}

UNIT_NORMALIZATION_MAP = {
    **MASS_UNITS,
    **VOLUME_UNITS,
    **DISCRETE_UNITS,
}


def parse_quantity(val: Any) -> QuantityParseResult:
    """Parse recipe ingredient quantities into floating point values with audit metadata.

    Supports:
    - Direct numeric integers/floats (e.g., '1', '2.5')
    - Simple fractions (e.g., '1/2', '3/4')
    - Mixed fractions (e.g., '1 1/2', '2 1/4')
    - Known unspaced mixed fraction anomalies (e.g., '11/2' -> 1.5)
    - Missing quantities (explicitly returns MISSING_QUANTITY, not 0)
    """
    if val is None:
        return QuantityParseResult(
            parsed_quantity=None,
            parse_status="MISSING_QUANTITY",
            original_quantity="",
            warning="Quantity is missing (None)",
        )

    # Handle pandas / numpy NaN or empty string
    val_str = str(val).strip()
    if val_str == "" or val_str.lower() in ("nan", "none", "<na>"):
        return QuantityParseResult(
            parsed_quantity=None,
            parse_status="MISSING_QUANTITY",
            original_quantity=val_str,
            warning="Quantity is missing or blank",
        )

    # 1. Check known unspaced mixed-fraction anomalies first
    if val_str in KNOWN_UNSPACED_FRACTION_ANOMALIES:
        qty = KNOWN_UNSPACED_FRACTION_ANOMALIES[val_str]
        return QuantityParseResult(
            parsed_quantity=qty,
            parse_status="PARSED_ANOMALY",
            original_quantity=val_str,
            warning=f"Known unspaced fraction anomaly '{val_str}' normalized to {qty}",
        )

    # 2. Direct numeric (float / integer)
    try:
        numeric_val = float(val_str)
        if numeric_val < 0:
            return QuantityParseResult(
                parsed_quantity=None,
                parse_status="PARSE_ERROR",
                original_quantity=val_str,
                warning=f"Negative quantity value: {numeric_val}",
            )
        return QuantityParseResult(
            parsed_quantity=numeric_val,
            parse_status="PARSED_NUMERIC",
            original_quantity=val_str,
        )
    except ValueError:
        pass

    # 3. Simple fractions (e.g. '1/2', '3/4', '1 / 2')
    fraction_match = re.match(r"^(\d+)\s*/\s*(\d+)$", val_str)
    if fraction_match:
        numerator = int(fraction_match.group(1))
        denominator = int(fraction_match.group(2))
        if denominator == 0:
            return QuantityParseResult(
                parsed_quantity=None,
                parse_status="PARSE_ERROR",
                original_quantity=val_str,
                warning="Fraction with zero denominator",
            )
        qty = float(Fraction(numerator, denominator))
        return QuantityParseResult(
            parsed_quantity=qty,
            parse_status="PARSED_FRACTION",
            original_quantity=val_str,
        )

    # 4. Mixed fractions (e.g. '1 1/2', '2 1/4', '1-1/2')
    # Support both whitespace separation and hyphenated mixed fractions (e.g. '1-1/2')
    mixed_match = re.match(r"^(\d+)[\s\-]+(\d+)\s*/\s*(\d+)$", val_str)
    if mixed_match:
        whole = int(mixed_match.group(1))
        numerator = int(mixed_match.group(2))
        denominator = int(mixed_match.group(3))
        if denominator == 0:
            return QuantityParseResult(
                parsed_quantity=None,
                parse_status="PARSE_ERROR",
                original_quantity=val_str,
                warning="Mixed fraction with zero denominator",
            )
        qty = float(whole + Fraction(numerator, denominator))
        return QuantityParseResult(
            parsed_quantity=qty,
            parse_status="PARSED_MIXED_FRACTION",
            original_quantity=val_str,
        )

    # 5. Unparseable format
    return QuantityParseResult(
        parsed_quantity=None,
        parse_status="PARSE_ERROR",
        original_quantity=val_str,
        warning=f"Cannot parse quantity string: '{val_str}'",
    )


def normalize_unit(unit_str: Optional[str]) -> Optional[str]:
    """Normalize recipe unit strings into canonical unit keys."""
    if unit_str is None:
        return None

    cleaned = str(unit_str).strip().lower()
    if cleaned in ("", "nan", "none", "<na>"):
        return None

    return UNIT_NORMALIZATION_MAP.get(cleaned, cleaned)
