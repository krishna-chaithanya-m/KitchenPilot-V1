"""Ingredient Matcher for KitchenPilot-V1 Recommendation Engine.

Computes ingredient-based match scores, available ingredient coverage,
and missing/matched ingredient sets using canonical mappings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from src.recommendation.config import RecommendationConfig


@dataclass
class IngredientMatchResult:
    """Detailed matching result for a single recipe against user ingredients."""
    match_score: float
    available_coverage: float
    matched_ingredients: List[str] = field(default_factory=list)
    missing_ingredients: List[str] = field(default_factory=list)
    required_matched: List[str] = field(default_factory=list)
    required_missing: List[str] = field(default_factory=list)
    disliked_found: List[str] = field(default_factory=list)
    satisfies_required: bool = True


class IngredientMatcher:
    """Matches user-provided ingredients against canonical recipe ingredients."""

    def __init__(self, config: Optional[RecommendationConfig] = None) -> None:
        self.config = config or RecommendationConfig()
        self._canonical_vocab: Set[str] = set()
        self._alias_to_canonical: Dict[str, str] = {}
        self._recipe_canonical_map: Dict[str, Set[str]] = {}
        self._recipe_all_ingredients: Dict[str, List[str]] = {}
        self._load_mappings()

    def _clean_str(self, text: any) -> str:
        """Lowercase and normalize whitespace/punctuation for matching."""
        if text is None or pd.isna(text):
            return ""
        s = str(text).strip()
        if s.lower() == "nan" or not s:
            return ""
        s = re.sub(r"[^a-zA-Z0-9\s]", " ", s.lower())
        return re.sub(r"\s+", " ", s).strip()

    def _load_mappings(self) -> None:
        """Load canonical ingredients and index recipes by canonical ingredient sets."""
        if self.config.ingredients_path.is_file():
            ing_df = pd.read_csv(self.config.ingredients_path)
            for _, row in ing_df.iterrows():
                cname = self._clean_str(row["canonical_name"])
                if cname:
                    self._canonical_vocab.add(cname)
                    self._alias_to_canonical[cname] = cname
                    disp = self._clean_str(row.get("display_name", ""))
                    if disp:
                        self._alias_to_canonical[disp] = cname

        linked_df = pd.read_csv(self.config.linked_ingredients_path)
        for _, row in linked_df.iterrows():
            rid = str(row["recipe_id"]).strip()
            if rid not in self._recipe_canonical_map:
                self._recipe_canonical_map[rid] = set()
                self._recipe_all_ingredients[rid] = []

            canon = self._clean_str(row.get("canonical_ingredient", ""))
            disp = self._clean_str(row.get("display_name", ""))
            ing = self._clean_str(row.get("ingredient", ""))

            if canon:
                self._canonical_vocab.add(canon)
                self._alias_to_canonical[canon] = canon
                self._recipe_canonical_map[rid].add(canon)
                if disp:
                    self._alias_to_canonical[disp] = canon
                if ing:
                    self._alias_to_canonical[ing] = canon

            # Best readable name for display in explanations
            best_name = canon or disp or ing
            if best_name and best_name not in self._recipe_all_ingredients[rid]:
                self._recipe_all_ingredients[rid].append(best_name)

    def resolve_ingredient(self, query: str) -> str:
        """Resolve a raw ingredient query string to its canonical name if known."""
        cleaned = self._clean_str(query)
        if not cleaned:
            return ""

        # Direct match
        if cleaned in self._alias_to_canonical:
            return self._alias_to_canonical[cleaned]

        # Simple plural stripping (e.g. tomatoes -> tomato, onions -> onion)
        if cleaned.endswith("es") and cleaned[:-2] in self._alias_to_canonical:
            return self._alias_to_canonical[cleaned[:-2]]
        if cleaned.endswith("s") and cleaned[:-1] in self._alias_to_canonical:
            return self._alias_to_canonical[cleaned[:-1]]

        # Substring search against canonical vocab
        for cname in self._canonical_vocab:
            if cname in cleaned or cleaned in cname:
                return cname

        return cleaned

    def resolve_ingredient_list(self, items: Optional[List[str]]) -> Set[str]:
        """Resolve a list of ingredients into a set of canonical/normalized names."""
        if not items:
            return set()
        resolved = set()
        for item in items:
            r = self.resolve_ingredient(item)
            if r:
                resolved.add(r)
        return resolved

    def match_recipe(
        self,
        recipe_id: str,
        available_ingredients: Optional[List[str]] = None,
        required_ingredients: Optional[List[str]] = None,
        preferred_ingredients: Optional[List[str]] = None,
        disliked_ingredients: Optional[List[str]] = None,
    ) -> IngredientMatchResult:
        """Compute matching metrics for a single recipe."""
        recipe_canons = self._recipe_canonical_map.get(recipe_id, set())
        all_ings = self._recipe_all_ingredients.get(recipe_id, [])

        avail_set = self.resolve_ingredient_list(available_ingredients)
        req_set = self.resolve_ingredient_list(required_ingredients)
        pref_set = self.resolve_ingredient_list(preferred_ingredients)
        dislike_set = self.resolve_ingredient_list(disliked_ingredients)

        # 1. Required ingredients matching
        req_matched = [r for r in req_set if r in recipe_canons]
        req_missing = [r for r in req_set if r not in recipe_canons]
        satisfies_req = len(req_missing) == 0

        if req_set:
            req_score = len(req_matched) / len(req_set)
        else:
            req_score = 1.0

        # 2. Available ingredients matching
        if avail_set:
            matched_avail = [a for a in avail_set if a in recipe_canons]
            avail_coverage = len(matched_avail) / len(avail_set)
            # Missing ingredients are recipe canonical ingredients not in available list
            missing_ings = [i for i in recipe_canons if i not in avail_set]
            matched_ings = matched_avail
        else:
            avail_coverage = 1.0
            missing_ings = []
            matched_ings = list(recipe_canons)

        # 3. Disliked ingredients
        disliked_found = [d for d in dislike_set if d in recipe_canons]

        # 4. Final ingredient match score calculation
        # If required ingredients are specified, they dictate the match score
        if req_set:
            match_score = req_score
        elif avail_set:
            match_score = avail_coverage
        elif pref_set:
            matched_pref = [p for p in pref_set if p in recipe_canons]
            match_score = len(matched_pref) / len(pref_set)
        else:
            match_score = 1.0

        # Soft penalty for disliked ingredients
        if disliked_found:
            match_score = max(0.0, match_score - (0.2 * len(disliked_found)))

        return IngredientMatchResult(
            match_score=float(min(1.0, max(0.0, match_score))),
            available_coverage=float(min(1.0, max(0.0, avail_coverage))),
            matched_ingredients=matched_ings,
            missing_ingredients=missing_ings,
            required_matched=req_matched,
            required_missing=req_missing,
            disliked_found=disliked_found,
            satisfies_required=satisfies_req,
        )

    def match_all_recipes(
        self,
        recipe_ids: List[str],
        available_ingredients: Optional[List[str]] = None,
        required_ingredients: Optional[List[str]] = None,
        preferred_ingredients: Optional[List[str]] = None,
        disliked_ingredients: Optional[List[str]] = None,
    ) -> Dict[str, IngredientMatchResult]:
        """Compute match results for a batch of recipe IDs."""
        return {
            rid: self.match_recipe(
                recipe_id=rid,
                available_ingredients=available_ingredients,
                required_ingredients=required_ingredients,
                preferred_ingredients=preferred_ingredients,
                disliked_ingredients=disliked_ingredients,
            )
            for rid in recipe_ids
        }
