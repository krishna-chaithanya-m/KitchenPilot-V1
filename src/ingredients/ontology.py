"""Canonical Ingredient Ontology engine for KitchenPilot."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd

from src.ingredients.aliases import AliasRegistry
from src.ingredients.models import (
    CanonicalIngredient,
    ParsedIngredientItem,
    ResolutionResult,
)
from src.ingredients.normalizer import (
    PREPARATION_KEYWORDS,
    normalize_ingredient_phrase,
    parse_raw_ingredient_line,
)

CANONICAL_FILE_PATH = Path("data/processed/ingredients.csv")
CNF_CURATION_PATH = Path("data/mappings/cnf_ingredient_mapping_curated.csv")

# Dietary and allergen rule inference based on category and canonical name
NON_VEGETARIAN_NAMES = {
    "chicken",
    "mutton",
    "fish",
    "prawn",
    "prawns",
    "shrimp",
    "shrimps",
    "crab",
    "crabs",
    "lobster",
    "egg",
    "eggs",
    "meat",
    "pork",
    "beef",
    "lamb",
    "bacon",
    "ham",
    "seafood",
    "squid",
    "keema",
    "kheema",
    "gosht",
    "maach",
    "machh",
    "machli",
    "murgh",
    "murg",
    "baida",
}
NON_VEGAN_CATEGORIES = {"dairy", "meat", "egg"}
NON_VEGAN_NAMES = {"milk", "curd", "yogurt", "paneer", "ghee", "butter", "cheese", "cream", "honey", "egg", "chicken"}

ALLERGEN_CATEGORY_MAP = {
    "dairy": ["dairy"],
    "egg": ["egg"],
    "nut": ["tree_nut"],
    "soy": ["soy"],
}

ALLERGEN_NAME_RULES = {
    "peanut": ["peanut"],
    "almond": ["tree_nut"],
    "cashew": ["tree_nut"],
    "walnut": ["tree_nut"],
    "pistachio": ["tree_nut"],
    "wheat": ["gluten"],
    "maida": ["gluten"],
    "semolina": ["gluten"],
    "rava": ["gluten"],
    "sooji": ["gluten"],
    "mustard": ["mustard"],
    "sesame": ["sesame"],
    "soy": ["soy"],
}

DEFAULT_UNITS = {
    "spice": "tsp",
    "herb": "sprig",
    "dairy": "ml",
    "oil": "tbsp",
    "liquid": "ml",
    "vegetable": "piece",
    "fruit": "piece",
    "grain": "g",
    "pulse": "g",
    "flour": "g",
    "nut": "g",
    "sweetener": "tsp",
    "meat": "g",
}


class IngredientOntology:
    """Production ontology maintaining canonical ingredients, dietary rules, and fast resolution."""

    def __init__(
        self,
        ingredients: Optional[List[CanonicalIngredient]] = None,
        alias_registry: Optional[AliasRegistry] = None,
    ):
        self._ingredients: Dict[str, CanonicalIngredient] = {}
        self._by_canonical_name: Dict[str, CanonicalIngredient] = {}
        self._alias_registry: AliasRegistry = alias_registry or AliasRegistry()

        if ingredients:
            for ing in ingredients:
                self.add_ingredient(ing)

    def add_ingredient(self, ing: CanonicalIngredient) -> None:
        """Add a canonical ingredient to the ontology index."""
        self._ingredients[ing.ingredient_id] = ing
        self._by_canonical_name[ing.canonical_name.lower()] = ing

    @classmethod
    def load(
        cls,
        canonical_path: Path = CANONICAL_FILE_PATH,
        cnf_curation_path: Path = CNF_CURATION_PATH,
        alias_registry: Optional[AliasRegistry] = None,
    ) -> "IngredientOntology":
        """Load canonical ontology from disk."""
        if alias_registry is None:
            alias_registry = AliasRegistry.load()

        ing_df = pd.read_csv(canonical_path, low_memory=False)

        # Load CNF references if available
        cnf_ref_map: Dict[str, str] = {}
        if cnf_curation_path.exists():
            cnf_df = pd.read_csv(cnf_curation_path, low_memory=False)
            for _, r in cnf_df.iterrows():
                cid = str(r.get("ingredient_id", "")).strip()
                code = str(r.get("cnf_food_code", "")).strip()
                name = str(r.get("cnf_food_name", "")).strip()
                if cid and code and code != "nan":
                    cnf_ref_map[cid] = f"CNF:{code} ({name})"

        ingredients: List[CanonicalIngredient] = []
        for _, row in ing_df.iterrows():
            cid = str(row["ingredient_id"]).strip()
            cname = str(row["canonical_name"]).strip()
            dname = str(row["display_name"]).strip()
            form = str(row.get("ingredient_form", "default")).strip()
            category = str(row.get("category", "other")).strip().lower()

            # Infer dietary properties
            name_lower = cname.lower()
            is_veg = not any(nv in name_lower for nv in NON_VEGETARIAN_NAMES) and category not in {"meat", "egg"}
            is_vegan = is_veg and (category not in NON_VEGAN_CATEGORIES) and not any(nv in name_lower for nv in NON_VEGAN_NAMES)

            # Infer allergens
            allergens: Set[str] = set()
            if category in ALLERGEN_CATEGORY_MAP:
                allergens.update(ALLERGEN_CATEGORY_MAP[category])
            for k, flags in ALLERGEN_NAME_RULES.items():
                if k in name_lower:
                    allergens.update(flags)

            default_unit = DEFAULT_UNITS.get(category, "g")
            nutrition_ref = cnf_ref_map.get(cid)

            # Retrieve mapped aliases
            aliases = [a.alias for a in alias_registry.get_aliases_for_id(cid)]

            ing = CanonicalIngredient(
                ingredient_id=cid,
                canonical_name=cname,
                display_name=dname,
                ingredient_form=form,
                category=category,
                vegetarian=is_veg,
                vegan=is_vegan,
                allergen_flags=sorted(list(allergens)),
                nutrition_reference=nutrition_ref,
                default_unit=default_unit,
                active=True,
                aliases=aliases,
            )
            ingredients.append(ing)

        return cls(ingredients=ingredients, alias_registry=alias_registry)

    def get_by_id(self, ingredient_id: str) -> Optional[CanonicalIngredient]:
        """Look up canonical ingredient by ID (e.g. ING00001)."""
        return self._ingredients.get(ingredient_id)

    def get_by_name(self, name: str) -> Optional[CanonicalIngredient]:
        """Look up canonical ingredient by exact canonical name."""
        return self._by_canonical_name.get(name.strip().lower())

    def all_ingredients(self) -> List[CanonicalIngredient]:
        """Return list of all registered canonical ingredients."""
        return list(self._ingredients.values())

    def resolve(self, text: str) -> ResolutionResult:
        """Resolve a raw or normalized text query to a canonical ingredient."""
        trace: List[str] = []
        raw_clean = text.strip()
        if not raw_clean:
            return ResolutionResult(trace=["empty_query"])

        clean_lower = raw_clean.lower()

        # 1. Exact canonical name match
        if clean_lower in self._by_canonical_name:
            ing = self._by_canonical_name[clean_lower]
            trace.append(f"exact_canonical_match:'{ing.canonical_name}'")
            return ResolutionResult(
                canonical_ingredient=ing,
                matched_alias=None,
                confidence=1.0,
                match_method="EXACT_CANONICAL",
                trace=trace,
            )

        # 2. Alias lookup
        alias = self._alias_registry.lookup(clean_lower)
        if alias:
            ing = self.get_by_id(alias.canonical_ingredient_id)
            if ing:
                trace.append(f"alias_match:'{alias.alias}'->{alias.canonical_ingredient_id}")
                return ResolutionResult(
                    canonical_ingredient=ing,
                    matched_alias=alias,
                    confidence=alias.confidence,
                    match_method="ALIAS_REGISTRY",
                    trace=trace,
                )

        # 3. Strip preparation prefix/suffix if present
        for prep_kw in PREPARATION_KEYWORDS:
            if clean_lower.startswith(prep_kw + " ") and clean_lower not in {"green chilli", "red chilli", "dry red chilli"}:
                stripped = clean_lower[len(prep_kw) + 1:].strip()
                trace.append(f"stripped_prep_prefix:'{prep_kw}'")
                sub_res = self.resolve(stripped)
                if sub_res.is_resolved:
                    sub_res.trace = trace + sub_res.trace
                    return sub_res
            elif clean_lower.endswith(" " + prep_kw) and clean_lower not in {"red chilli powder", "black pepper powder"}:
                stripped = clean_lower[:-len(prep_kw) - 1].strip()
                trace.append(f"stripped_prep_suffix:'{prep_kw}'")
                sub_res = self.resolve(stripped)
                if sub_res.is_resolved:
                    sub_res.trace = trace + sub_res.trace
                    return sub_res

        # 4. Normalized phrase match
        norm_name, norm_trace = normalize_ingredient_phrase(clean_lower)
        trace.extend(norm_trace)

        if norm_name in self._by_canonical_name:
            ing = self._by_canonical_name[norm_name]
            trace.append(f"normalized_phrase_canonical_match:'{norm_name}'")
            return ResolutionResult(
                canonical_ingredient=ing,
                matched_alias=None,
                confidence=0.90,
                match_method="NORMALIZED_CANONICAL",
                trace=trace,
            )

        norm_alias = self._alias_registry.lookup(norm_name)
        if norm_alias:
            ing = self.get_by_id(norm_alias.canonical_ingredient_id)
            if ing:
                trace.append(f"normalized_alias_match:'{norm_name}'->{norm_alias.canonical_ingredient_id}")
                return ResolutionResult(
                    canonical_ingredient=ing,
                    matched_alias=norm_alias,
                    confidence=norm_alias.confidence * 0.95,
                    match_method="NORMALIZED_ALIAS",
                    trace=trace,
                )

        trace.append(f"unresolved:'{text}'")
        return ResolutionResult(
            canonical_ingredient=None,
            matched_alias=None,
            confidence=0.0,
            match_method="NONE",
            trace=trace,
        )

    def parse_and_resolve(self, raw_line: str) -> ParsedIngredientItem:
        """Parse raw ingredient line preserving quantity, unit, and preparation, then resolve canonical ingredient."""
        item = parse_raw_ingredient_line(raw_line)
        res = self.resolve(item.ingredient)

        if res.is_resolved and res.canonical_ingredient:
            item.canonical_ingredient_id = res.canonical_ingredient.ingredient_id
            if res.match_method == "EXACT_CANONICAL":
                item.mapping_status = "MAPPED_CANONICAL"
            else:
                item.mapping_status = "MAPPED_ALIAS"
        else:
            item.mapping_status = "REVIEW_REQUIRED" if item.ingredient else "UNMAPPED"

        item.normalization_trace.extend(res.trace)
        return item

    def is_vegetarian(self, ingredient_id: str) -> bool:
        """Check if an ingredient is vegetarian."""
        ing = self.get_by_id(ingredient_id)
        return ing.vegetarian if ing else False

    def is_vegan(self, ingredient_id: str) -> bool:
        """Check if an ingredient is vegan."""
        ing = self.get_by_id(ingredient_id)
        return ing.vegan if ing else False

    def get_allergen_flags(self, ingredient_id: str) -> List[str]:
        """Get declared allergens for an ingredient."""
        ing = self.get_by_id(ingredient_id)
        return ing.allergen_flags if ing else []
