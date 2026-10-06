"""Ingredient Matching and Constraint Subsystem for KitchenPilot-V1.

Implements deterministic ontology-backed ingredient resolution, alias matching,
exclusion checks (HARD), requirement checks (HARD), preferred ingredient scoring (SOFT),
and pantry availability coverage calculation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from src.constraints.models import (
    IngredientConstraints,
    IngredientMatchResult,
    MatchType,
    PantryMatchMetrics,
)
from src.ingredients.normalizer import normalize_ingredient_phrase
from src.ingredients.ontology import IngredientOntology

logger = logging.getLogger("kitchenpilot.constraints.ingredients")

LINKED_INGREDIENTS_PATH = Path("data/processed/recipe_ingredients_linked.csv")


def _clean_phrase(text: str) -> str:
    """Helper to unpack normalized string from normalizer tuple."""
    if not text:
        return ""
    norm, _ = normalize_ingredient_phrase(text)
    return norm.strip().lower()


class IngredientConstraintMatcher:
    """Manages ingredient resolution, requirement enforcement, and pantry matching."""

    def __init__(
        self,
        ontology: Optional[IngredientOntology] = None,
        linked_ingredients_path: Path = LINKED_INGREDIENTS_PATH,
    ) -> None:
        self.ontology = ontology or IngredientOntology.load()
        self.linked_ingredients_path = linked_ingredients_path

        # Recipe mappings: recipe_id -> sets of ingredient identifiers
        self._recipe_canonical_ids: Dict[str, Set[str]] = {}
        self._recipe_canonical_names: Dict[str, Set[str]] = {}
        self._recipe_raw_ingredients: Dict[str, List[str]] = {}
        self._recipe_clean_ingredients: Dict[str, List[str]] = {}

        self._load_recipe_ingredients()

    def _load_recipe_ingredients(self) -> None:
        """Load and index recipe ingredient links from authoritative CSV."""
        if not self.linked_ingredients_path.is_file():
            logger.warning("Linked ingredients file not found: %s", self.linked_ingredients_path)
            return

        df = pd.read_csv(self.linked_ingredients_path, low_memory=False)
        for _, row in df.iterrows():
            rid = str(row["recipe_id"]).strip()
            cid = str(row.get("ingredient_id", "")).strip()
            cname = str(row.get("canonical_ingredient", "")).strip().lower()
            clean_ing = str(row.get("ingredient", "")).strip().lower()
            orig = str(row.get("original_ingredient", "")).strip().lower()

            if rid not in self._recipe_canonical_ids:
                self._recipe_canonical_ids[rid] = set()
                self._recipe_canonical_names[rid] = set()
                self._recipe_raw_ingredients[rid] = []
                self._recipe_clean_ingredients[rid] = []

            if cid and cid != "nan":
                self._recipe_canonical_ids[rid].add(cid)
            if cname and cname != "nan":
                self._recipe_canonical_names[rid].add(cname)
            if clean_ing and clean_ing != "nan":
                self._recipe_clean_ingredients[rid].append(clean_ing)
            if orig and orig != "nan":
                self._recipe_raw_ingredients[rid].append(orig)

    def resolve_ingredient(self, query: str) -> IngredientMatchResult:
        """Resolve an ingredient query through the deterministic ontology hierarchy:

        1. Direct canonical ingredient ID match (e.g. 'ING00046')
        2. Exact canonical name match (e.g. 'cumin')
        3. Curated alias lookup (e.g. 'jeera' -> cumin)
        4. Normalized phrase match
        5. Safe lexical fallback
        6. Unresolved
        """
        raw = query.strip()
        if not raw:
            return IngredientMatchResult(query_ingredient=query, match_type=MatchType.UNRESOLVED)

        # 1. Direct ID match
        if raw.upper().startswith("ING") and len(raw) == 8:
            ing = self.ontology.get_by_id(raw.upper())
            if ing:
                return IngredientMatchResult(
                    query_ingredient=query,
                    canonical_ingredient_id=ing.ingredient_id,
                    canonical_name=ing.canonical_name,
                    match_type=MatchType.EXACT,
                    confidence=1.0,
                    source="id_lookup",
                )

        # 2. Ontology Resolution (handles exact name, alias, and normalization)
        res = self.ontology.resolve(raw)
        if res.canonical_ingredient:
            ing = res.canonical_ingredient
            match_type_map = {
                "EXACT_CANONICAL": MatchType.EXACT,
                "EXACT_ALIAS": MatchType.ALIAS,
                "NORMALIZED_ALIAS": MatchType.ALIAS,
                "NORMALIZED_TEXT": MatchType.NORMALIZED,
            }
            m_type = match_type_map.get(res.match_method, MatchType.CANONICAL)
            return IngredientMatchResult(
                query_ingredient=query,
                canonical_ingredient_id=ing.ingredient_id,
                canonical_name=ing.canonical_name,
                match_type=m_type,
                confidence=res.confidence,
                source=f"ontology:{res.match_method}",
            )

        # 3. Safe Lexical Fallback: exact whole-word search against canonical dictionary
        clean_norm = _clean_phrase(raw)
        if clean_norm:
            ing_direct = self.ontology.get_by_name(clean_norm)
            if ing_direct:
                return IngredientMatchResult(
                    query_ingredient=query,
                    canonical_ingredient_id=ing_direct.ingredient_id,
                    canonical_name=ing_direct.canonical_name,
                    match_type=MatchType.NORMALIZED,
                    confidence=0.9,
                    source="normalized_lookup",
                )

        return IngredientMatchResult(
            query_ingredient=query,
            match_type=MatchType.UNRESOLVED,
            confidence=0.0,
            source="none",
        )

    def recipe_contains_ingredient(self, recipe_id: str, query_ingredient: str) -> bool:
        """Check whether a recipe contains the given ingredient via ontology or text."""
        resolved = self.resolve_ingredient(query_ingredient)

        # Check by canonical ID
        if resolved.canonical_ingredient_id:
            cids = self._recipe_canonical_ids.get(recipe_id, set())
            if resolved.canonical_ingredient_id in cids:
                return True

        # Check by canonical name
        if resolved.canonical_name:
            cnames = self._recipe_canonical_names.get(recipe_id, set())
            if resolved.canonical_name.lower() in cnames:
                return True

        # Check clean ingredient names and raw ingredient text for whole-word / token match
        norm_query = _clean_phrase(query_ingredient)
        if not norm_query:
            norm_query = query_ingredient.strip().lower()

        clean_ings = self._recipe_clean_ingredients.get(recipe_id, [])
        for clean_ing in clean_ings:
            if norm_query == clean_ing or norm_query in clean_ing:
                return True

        raw_ings = self._recipe_raw_ingredients.get(recipe_id, [])
        for raw_ing in raw_ings:
            if norm_query in raw_ing:
                return True

        return False

    def evaluate_ingredient_constraints(
        self,
        recipe_id: str,
        constraints: IngredientConstraints,
    ) -> Tuple[bool, List[str], List[str], PantryMatchMetrics]:
        """Evaluate ingredient exclusions, requirements, and pantry coverage.

        Returns:
            (passed, hard_failures, soft_matches, pantry_metrics)
        """
        hard_failures: List[str] = []
        soft_matches: List[str] = []

        # 1. HARD Excluded Ingredients Check
        for exc in constraints.excluded_ingredients:
            if not exc.strip():
                continue
            if self.recipe_contains_ingredient(recipe_id, exc):
                hard_failures.append(f"Contains excluded ingredient: '{exc.strip()}'")

        # 2. HARD Required Ingredients Check
        for req in constraints.required_ingredients:
            if not req.strip():
                continue
            if not self.recipe_contains_ingredient(recipe_id, req):
                hard_failures.append(f"Missing required ingredient: '{req.strip()}'")

        # 3. SOFT Preferred Ingredients Check
        for pref in constraints.preferred_ingredients:
            if not pref.strip():
                continue
            if self.recipe_contains_ingredient(recipe_id, pref):
                soft_matches.append(f"Contains preferred ingredient: '{pref.strip()}'")

        # 4. Pantry Availability Matching
        pantry_metrics = self.calculate_pantry_metrics(recipe_id, constraints.available_ingredients)

        # 5. Pantry Hard Mode Check (require_all_ingredients)
        if constraints.require_all_ingredients and constraints.available_ingredients:
            if pantry_metrics.recipe_total_count > 0 and pantry_metrics.coverage_ratio < 1.0:
                missing_str = ", ".join(pantry_metrics.missing_ingredients[:3])
                hard_failures.append(
                    f"Pantry coverage ({pantry_metrics.matched_count}/{pantry_metrics.recipe_total_count}) "
                    f"is incomplete. Missing: {missing_str}"
                )

        passed = len(hard_failures) == 0
        return passed, hard_failures, soft_matches, pantry_metrics

    def calculate_pantry_metrics(
        self,
        recipe_id: str,
        available_ingredients: Sequence[str],
    ) -> PantryMatchMetrics:
        """Calculate quantitative pantry availability metrics for a recipe."""
        clean_avail = [a.strip() for a in available_ingredients if a.strip()]
        recipe_clean = self._recipe_clean_ingredients.get(recipe_id, [])
        recipe_canons = self._recipe_canonical_names.get(recipe_id, set())

        # Determine total unique recipe items
        total_items = list(set(recipe_clean) | recipe_canons)
        if not total_items:
            # Fallback to linked count or 1
            total_count = max(1, len(recipe_clean))
            return PantryMatchMetrics(
                matched_count=0,
                recipe_total_count=total_count,
                coverage_ratio=0.0,
                matched_ingredients=[],
                missing_ingredients=[],
            )

        if not clean_avail:
            return PantryMatchMetrics(
                matched_count=0,
                recipe_total_count=len(total_items),
                coverage_ratio=0.0,
                matched_ingredients=[],
                missing_ingredients=sorted(list(total_items)),
            )

        matched_items: Set[str] = set()
        for avail in clean_avail:
            res = self.resolve_ingredient(avail)
            avail_canon = res.canonical_name.lower() if res.canonical_name else None
            avail_clean = _clean_phrase(avail)

            for item in total_items:
                item_lower = item.lower()
                if avail_canon and (avail_canon == item_lower or avail_canon in item_lower):
                    matched_items.add(item)
                elif avail_clean and (avail_clean == item_lower or avail_clean in item_lower):
                    matched_items.add(item)
                elif avail.lower() in item_lower or item_lower in avail.lower():
                    matched_items.add(item)

        missing_items = [item for item in total_items if item not in matched_items]
        coverage = len(matched_items) / max(1, len(total_items))

        return PantryMatchMetrics(
            matched_count=len(matched_items),
            recipe_total_count=len(total_items),
            coverage_ratio=min(1.0, max(0.0, coverage)),
            matched_ingredients=sorted(list(matched_items)),
            missing_ingredients=sorted(missing_items),
        )
