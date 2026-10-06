"""Deterministic, auditable ingredient normalizer and line parser."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from src.ingredients.models import ParsedIngredientItem
from src.nutrition.quantity_parser import parse_quantity, UNIT_NORMALIZATION_MAP


# Preparation keywords that qualify the state of an ingredient rather than its core identity
PREPARATION_KEYWORDS = [
    "finely chopped", "thinly sliced", "roughly chopped", "coarsely crushed",
    "freshly ground", "dry roasted", "deep fried", "shallow fried",
    "chopped", "sliced", "diced", "grated", "crushed", "minced", "shredded",
    "pureed", "mashed", "boiled", "cooked", "roasted", "soaked", "fried",
    "steamed", "blanched", "deseeded", "slit", "peeled", "beaten", "whisked",
    "melted", "toasted", "warm", "cold", "chilled", "sifted"
]

# Controlled plural singularization mapping
SAFE_PLURALS = {
    "onions": "onion",
    "tomatoes": "tomato",
    "potatoes": "potato",
    "chillies": "chilli",
    "chillis": "chilli",
    "chickpeas": "chickpea",
    "lentils": "lentil",
    "cloves": "clove",
    "leaves": "leaf",
    "seeds": "seed",
    "pods": "pod",
    "peppercorns": "peppercorn",
    "carrots": "carrot",
    "cucumbers": "cucumber",
    "mushrooms": "mushroom",
    "cashews": "cashew",
    "almonds": "almond",
    "walnuts": "walnut",
    "pistachios": "pistachio",
    "peanuts": "peanut",
    "raisins": "raisin",
    "apples": "apple",
    "bananas": "banana",
    "lemons": "lemon",
    "limes": "lime",
    "noodles": "noodle",
    "beans": "bean",
    "peas": "pea",
    "berries": "berry",
    "chilies": "chilli",
    "capsicums": "capsicum",
}

# Inviolate distinct phrases that must NEVER be stripped or cross-merged
DISTINCT_CULINARY_PHRASES = {
    "green chilli", "red chilli", "dry red chilli", "chilli powder", "red chilli powder",
    "kashmiri red chilli", "black pepper", "white pepper", "bell pepper",
    "coriander powder", "coriander leaf", "coriander leaves", "coriander seed", "coriander seeds",
    "cumin seed", "cumin seeds", "cumin powder", "mustard seed", "mustard seeds", "mustard oil",
    "garam masala", "chaat masala", "chana masala", "sambar powder", "rasam powder",
    "coconut milk", "coconut oil", "dry coconut", "fresh coconut",
    "baking soda", "baking powder", "brown sugar", "powdered sugar",
}


def normalize_text_unicode(text: str) -> str:
    """Normalize unicode characters and whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = " ".join(text.split())
    return text


def extract_parenthetical_info(text: str) -> Tuple[str, List[str]]:
    """Extract parenthetical notes (e.g., '(haldi)', '(besan)') while returning cleaned text."""
    parentheticals = re.findall(r"\(([^)]+)\)", text)
    cleaned = re.sub(r"\([^)]*\)", "", text)
    cleaned = " ".join(cleaned.split())
    return cleaned, [p.strip() for p in parentheticals if p.strip()]


def singularize_token(word: str) -> Tuple[str, Optional[str]]:
    """Safely singularize a single token if it matches a known controlled plural."""
    w_lower = word.lower()
    if w_lower in SAFE_PLURALS:
        singular = SAFE_PLURALS[w_lower]
        return singular, f"singularized:{word}->{singular}"
    return word, None


def normalize_ingredient_phrase(phrase: str) -> Tuple[str, List[str]]:
    """Apply deterministic, auditable normalization to an ingredient phrase."""
    trace: List[str] = []
    text = normalize_text_unicode(phrase).lower()
    trace.append(f"initial_clean:'{text}'")

    # Check inviolate phrases first to prevent over-normalization
    for protected in DISTINCT_CULINARY_PHRASES:
        if text == protected:
            trace.append(f"protected_phrase_exact_match:'{protected}'")
            return protected, trace

    # Extract parentheticals
    text, parentheticals = extract_parenthetical_info(text)
    if parentheticals:
        trace.append(f"extracted_parentheticals:{parentheticals}")

    # Remove leading/trailing non-alphanumeric punctuation
    text = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", text)

    # Remove leading quantity/unit prefixes (e.g. 'to 3 tablespoons karela' -> 'karela')
    units_pattern = "|".join(sorted(UNIT_NORMALIZATION_MAP.keys(), key=len, reverse=True))
    prefix_pattern = rf"^(?:(?:to|approx\.?|approximately|about|around)\s+)?\d+(?:[-–/ ]\d+)*(?:\s*/\s*\d+)?(?:\.\d+)?\s*(?:(?:{units_pattern})\b\s*)?"
    prefix_match = re.match(prefix_pattern, text)
    if prefix_match and text not in DISTINCT_CULINARY_PHRASES:
        stripped = text[prefix_match.end():].strip()
        if stripped:
            trace.append(f"removed_quantity_prefix:'{text[:prefix_match.end()].strip()}'")
            text = stripped

    # Remove generic qualifiers like 'fresh', 'raw', 'organic' if not protected
    for qualifier in ["fresh", "raw", "organic"]:
        if text.startswith(qualifier + " ") and text not in DISTINCT_CULINARY_PHRASES:
            text = text[len(qualifier) + 1:].strip()
            trace.append(f"removed_qualifier:'{qualifier}'")

    # Token-level singularization
    tokens = text.split()
    new_tokens = []
    for tok in tokens:
        sing, rule = singularize_token(tok)
        new_tokens.append(sing)
        if rule:
            trace.append(rule)

    normalized = " ".join(new_tokens)
    trace.append(f"final_normalized:'{normalized}'")
    return normalized, trace


def parse_raw_ingredient_line(raw_text: str) -> ParsedIngredientItem:
    """Parse a raw recipe ingredient string preserving quantity, unit, name, and preparation."""
    trace: List[str] = [f"input:'{raw_text}'"]
    clean_text = normalize_text_unicode(raw_text)

    # 1. Check for 'to taste' or qualitative seasoning
    if re.search(r"\bto taste\b|\bas required\b|\bas needed\b|\bfor seasoning\b", clean_text, re.IGNORECASE):
        # Extract seasoning name before delimiter or qualifier
        base_match = re.split(r"[-–—]|,\s*to taste|\bto taste\b|\bas required\b", clean_text, flags=re.IGNORECASE)[0].strip()
        norm_name, norm_trace = normalize_ingredient_phrase(base_match)
        trace.extend(norm_trace)
        return ParsedIngredientItem(
            original_text=raw_text,
            quantity=None,
            unit=None,
            ingredient=norm_name,
            preparation_state="to taste",
            mapping_status="UNMAPPED",
            normalization_trace=trace,
        )

    # 2. Pre-normalize mixed fractions like '1-1 / 2' or '2-1/2' before splitting hyphens
    clean_text = re.sub(r"(\d+)\s*[-–—]\s*(\d+\s*/\s*\d+)", r"\1 \2", clean_text)

    # 3. Extract preparation state if indicated by hyphen or comma (only when hyphen is not between digits)
    prep_state: Optional[str] = None
    core_part = clean_text
    parts = re.split(r"(?<!\d)\s*[-–—]\s*(?!\d)", clean_text, maxsplit=1)
    if len(parts) > 1:
        core_part = parts[0].strip()
        prep_state = parts[1].strip()
        trace.append(f"split_hyphen_prep:'{prep_state}'")
    elif ", " in clean_text:
        # Check if the portion after comma is a known preparation keyword
        comma_parts = clean_text.split(", ", 1)
        if any(kw in comma_parts[1].lower() for kw in PREPARATION_KEYWORDS):
            core_part = comma_parts[0].strip()
            prep_state = comma_parts[1].strip()
            trace.append(f"split_comma_prep:'{prep_state}'")

    # 4. Extract quantity from the start of core_part
    # Regex matching numbers, mixed numbers, fractions, and optional leading range words:
    # e.g. 'to 3 tablespoons', '2-1 / 2', '1 1/2', '1/2', '500', '1.5'
    qty_regex = r"^(?:(?:to|approx\.?|approximately|about|around)\s+)?(\d+(?:[-–/ ]\d+)*(?:\s*/\s*\d+)?(?:\.\d+)?)\s*(.*)$"
    match = re.match(qty_regex, core_part, re.IGNORECASE)

    parsed_qty: Optional[float] = None
    remainder: str = core_part

    if match:
        raw_num = match.group(1).strip()
        rem = match.group(2).strip()

        # Parse quantity using project parser
        qty_res = parse_quantity(raw_num)
        if qty_res.parsed_quantity is not None:
            parsed_qty = qty_res.parsed_quantity
            remainder = rem
            trace.append(f"parsed_quantity:{parsed_qty} from '{raw_num}'")

    # 4. Extract unit from remainder
    tokens = remainder.split()
    detected_unit: Optional[str] = None
    ingredient_tokens: List[str] = tokens

    if tokens:
        first_token = tokens[0].lower().rstrip(".,")
        # Also check two-word units if any
        if first_token in UNIT_NORMALIZATION_MAP:
            detected_unit = UNIT_NORMALIZATION_MAP[first_token]
            ingredient_tokens = tokens[1:]
            trace.append(f"matched_unit:'{detected_unit}' from '{tokens[0]}'")

    candidate_name = " ".join(ingredient_tokens).strip()

    # 5. Check if preparation keyword is embedded in the candidate name (e.g. 'chopped onion')
    for prep_kw in PREPARATION_KEYWORDS:
        if candidate_name.lower().startswith(prep_kw + " "):
            prep_state = prep_kw if not prep_state else f"{prep_state}, {prep_kw}"
            candidate_name = candidate_name[len(prep_kw) + 1:].strip()
            trace.append(f"extracted_prefix_prep:'{prep_kw}'")
            break
        elif candidate_name.lower().endswith(" " + prep_kw):
            prep_state = prep_kw if not prep_state else f"{prep_state}, {prep_kw}"
            candidate_name = candidate_name[:-len(prep_kw) - 1].strip()
            trace.append(f"extracted_suffix_prep:'{prep_kw}'")
            break

    norm_name, norm_trace = normalize_ingredient_phrase(candidate_name)
    trace.extend(norm_trace)

    return ParsedIngredientItem(
        original_text=raw_text,
        quantity=parsed_qty,
        unit=detected_unit,
        ingredient=norm_name,
        preparation_state=prep_state,
        mapping_status="UNMAPPED",
        normalization_trace=trace,
    )
