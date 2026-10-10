import pytest

from src.data.cuisine_policy import is_indian_cuisine, normalize_cuisine



@pytest.mark.parametrize(
    "cuisine",
    [
        "Indian",
        "North Indian Recipes",
        "South Indian Recipes",
        "Bengali Recipes",
        "Gujarati Recipes",
        "Udupi",
        "Coorg",
        "Malabar",
        "Kongunadu",
        "Nagaland",
        "Indo Chinese",
    ],
)
def test_approved_indian_cuisines_are_allowed(cuisine):
    assert is_indian_cuisine(cuisine) is True


@pytest.mark.parametrize(
    "cuisine",
    [
        "Mexican",
        "Chinese",
        "Italian Recipes",
        "Thai",
        "Continental",
        "Fusion",
        "World Breakfast",
        "American",
        "",
        None,
    ],
)
def test_non_indian_ambiguous_or_missing_cuisines_are_rejected(cuisine):
    assert is_indian_cuisine(cuisine) is False


def test_cuisine_matching_ignores_case_and_extra_whitespace():
    assert is_indian_cuisine("  NORTH   INDIAN RECIPES ") is True
    assert is_indian_cuisine("  mExIcAn ") is False
    assert normalize_cuisine("  NORTH   INDIAN RECIPES ") == "north indian recipes"
    assert normalize_cuisine("  mExIcAn ") == "mexican"
    assert normalize_cuisine("   ") is None
    assert normalize_cuisine("") is None
    assert normalize_cuisine(None) is None
