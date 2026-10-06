"""Tests for Ingredient Ontology, normalizer, and alias registry."""

from __future__ import annotations

import pandas as pd
import pytest

from src.ingredients.normalizer import (
    normalize_ingredient_phrase,
    parse_raw_ingredient_line,
)
from src.ingredients.ontology import IngredientOntology
from src.ingredients.validator import validate_ontology


def test_deterministic_normalization():
    norm1, trace1 = normalize_ingredient_phrase("onion")
    norm2, trace2 = normalize_ingredient_phrase("onions")
    assert norm1 == "onion"
    assert norm2 == "onion"
    assert any("singularized" in t for t in trace2)


def test_preserves_distinct_chilli_types():
    norm_green, _ = normalize_ingredient_phrase("green chilli")
    norm_red, _ = normalize_ingredient_phrase("red chilli")
    norm_powder, _ = normalize_ingredient_phrase("chilli powder")

    assert norm_green == "green chilli"
    assert norm_red == "red chilli"
    assert norm_powder == "chilli powder"
    assert norm_green != norm_red
    assert norm_red != norm_powder


def test_parse_raw_ingredient_line_quantity_and_prep():
    item = parse_raw_ingredient_line("2 tablespoon chopped onion")
    assert item.quantity == 2.0
    assert item.unit == "tbsp"
    assert item.ingredient == "onion"
    assert item.preparation_state == "chopped"


def test_parse_raw_ingredient_fraction():
    item = parse_raw_ingredient_line("1/2 teaspoon turmeric powder")
    assert item.quantity == 0.5
    assert item.unit == "tsp"
    assert item.ingredient == "turmeric powder"


def test_parse_raw_ingredient_mixed_fraction():
    item = parse_raw_ingredient_line("1-1 / 2 cups rice - cooked")
    assert item.quantity == 1.5
    assert item.unit == "cup"
    assert item.ingredient == "rice"
    assert item.preparation_state == "cooked"


def test_parse_raw_ingredient_seasoning():
    item = parse_raw_ingredient_line("Salt - to taste")
    assert item.quantity is None
    assert item.ingredient == "salt"
    assert item.preparation_state == "to taste"


def test_ontology_loading_and_resolution():
    ont = IngredientOntology.load()
    assert len(ont.all_ingredients()) == 129

    # Exact canonical match
    res_onion = ont.resolve("onion")
    assert res_onion.is_resolved
    assert res_onion.canonical_ingredient.ingredient_id == "ING00083"
    assert res_onion.match_method == "EXACT_CANONICAL"

    # Alias match
    res_onions = ont.resolve("onions")
    assert res_onions.is_resolved
    assert res_onions.canonical_ingredient.ingredient_id == "ING00083"

    # Preparation stripping match
    res_chopped = ont.resolve("chopped onion")
    assert res_chopped.is_resolved
    assert res_chopped.canonical_ingredient.ingredient_id == "ING00083"

    # Hindi / parenthetical alias match
    res_haldi = ont.resolve("haldi")
    assert res_haldi.is_resolved
    assert res_haldi.canonical_ingredient.canonical_name == "turmeric"

    # Bitter gourd canonical and alias resolution
    res_bg = ont.resolve("bitter gourd")
    assert res_bg.is_resolved
    assert res_bg.canonical_ingredient.canonical_name == "bitter gourd"
    assert res_bg.canonical_ingredient.ingredient_id == "ING00129"

    res_karela = ont.resolve("karela")
    assert res_karela.is_resolved
    assert res_karela.canonical_ingredient.canonical_name == "bitter gourd"

    res_pavakkai = ont.resolve("pavakkai")
    assert res_pavakkai.is_resolved
    assert res_pavakkai.canonical_ingredient.canonical_name == "bitter gourd"

    # Preparation / instruction / descriptor fragments must NOT resolve as aliases
    assert not ont.resolve("Small").is_resolved
    assert not ont.resolve("remove excess seeds from inside").is_resolved


def test_ontology_dietary_properties():
    ont = IngredientOntology.load()

    # Onion is veg & vegan
    assert ont.is_vegetarian("ING00083") is True
    assert ont.is_vegan("ING00083") is True

    # Chicken is non-veg & non-vegan
    assert ont.is_vegetarian("ING00027") is False
    assert ont.is_vegan("ING00027") is False

    # Ghee (dairy) is veg but not vegan
    ghee = ont.get_by_name("ghee")
    assert ghee is not None
    assert ont.is_vegetarian(ghee.ingredient_id) is True
    assert ont.is_vegan(ghee.ingredient_id) is False
    assert "dairy" in ont.get_allergen_flags(ghee.ingredient_id)

    # Bitter gourd is veg & vegan
    bg = ont.get_by_name("bitter gourd")
    assert bg is not None
    assert ont.is_vegetarian(bg.ingredient_id) is True
    assert ont.is_vegan(bg.ingredient_id) is True


def test_ontology_validation_report_live():
    ont = IngredientOntology.load()
    alias_df = pd.read_csv("data/mappings/ingredients/ingredient_aliases.csv")
    rep = validate_ontology(ont, alias_df)
    assert rep.is_valid
    assert rep.total_canonical_count == 129
    assert len(rep.duplicate_canonical_ids) == 0
    assert len(rep.orphan_aliases) == 0
