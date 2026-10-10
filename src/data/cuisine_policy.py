"""Shared policy for restricting KitchenPilot to Indian cuisine recipes."""

from __future__ import annotations

import re
from typing import Optional


INDIAN_CUISINES = frozenset({
    "indian",
    "north indian recipes",
    "south indian recipes",
    "bengali recipes",
    "maharashtrian recipes",
    "kerala recipes",
    "tamil nadu",
    "karnataka",
    "rajasthani",
    "andhra",
    "gujarati recipes",
    "goan recipes",
    "punjabi",
    "chettinad",
    "kashmiri",
    "mangalorean",
    "parsi recipes",
    "indo chinese",
    "awadhi",
    "oriya recipes",
    "sindhi",
    "konkan",
    "mughlai",
    "bihari",
    "hyderabadi",
    "assamese",
    "north east india recipes",
    "himachal",
    "udupi",
    "uttar pradesh",
    "coorg",
    "north karnataka",
    "coastal karnataka",
    "malabar",
    "lucknowi",
    "south karnataka",
    "malvani",
    "nagaland",
    "uttarakhand-north kumaon",
    "kongunadu",
    "haryana",
    "jharkhand",
})


def normalize_cuisine(cuisine: Optional[str]) -> Optional[str]:
    """Normalize cuisine label by collapsing whitespace, stripping, and casefolding."""
    if not isinstance(cuisine, str):
        return None
    normalized = re.sub(r"\s+", " ", cuisine).strip().casefold()
    return normalized if normalized else None


def is_indian_cuisine(cuisine: Optional[str]) -> bool:
    """Return True only for explicitly approved Indian cuisine labels."""
    norm = normalize_cuisine(cuisine)
    return norm in INDIAN_CUISINES if norm is not None else False
