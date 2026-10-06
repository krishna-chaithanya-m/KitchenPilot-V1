"""Ingredient alias compilation and registry management."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from src.cleaning.normalize_hindi_ingredients import HINDI_MAP
from src.ingredients.models import IngredientAlias
from src.ingredients.normalizer import (
    extract_parenthetical_info,
    normalize_ingredient_phrase,
)

ALIAS_FILE_PATH = Path("data/mappings/ingredients/ingredient_aliases.csv")
CANONICAL_FILE_PATH = Path("data/processed/ingredients.csv")
RECIPE_LINKS_PATH = Path("data/processed/recipe_ingredients_linked.csv")
CANDIDATE_MAPPING_PATH = Path("data/mappings/final_ingredient_mapping_validated.csv")


def compile_ingredient_aliases() -> pd.DataFrame:
    """Compile a clean, normalized alias table from authoritative project sources."""
    ing_df = pd.read_csv(CANONICAL_FILE_PATH, low_memory=False)
    cand_df = pd.read_csv(CANDIDATE_MAPPING_PATH, low_memory=False)
    ring_df = pd.read_csv(RECIPE_LINKS_PATH, low_memory=False)

    # Build canonical lookup
    canon_lookup: Dict[Any, str] = {}
    for _, row in ing_df.iterrows():
        cid = str(row["ingredient_id"]).strip()
        cname = str(row["canonical_name"]).strip().lower()
        cform = str(row["ingredient_form"]).strip().lower()
        canon_lookup[(cname, cform)] = cid
        if cform == "default":
            canon_lookup[cname] = cid

    seen_pairs: Set[Tuple[str, str]] = set()
    records: List[Dict[str, Any]] = []

    def _add(cid: str, raw_alias: str, source: str, confidence: float, status: str) -> None:
        norm, _ = normalize_ingredient_phrase(raw_alias)
        if not norm or not cid:
            return
        pair = (cid, norm)
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)
        records.append({
            "canonical_ingredient_id": cid,
            "alias": raw_alias.strip(),
            "normalized_alias": norm,
            "source": source,
            "confidence": float(confidence),
            "review_status": status,
        })

    # 1. Canonical database names
    for _, r in ing_df.iterrows():
        cid = str(r["ingredient_id"]).strip()
        _add(cid, str(r["canonical_name"]), "canonical_database", 1.0, "VALIDATED")
        if str(r["display_name"]).lower() != str(r["canonical_name"]).lower():
            _add(cid, str(r["display_name"]), "canonical_database", 1.0, "VALIDATED")

    # 2. Hindi translation lexicon
    for hindi_word, eng_term in HINDI_MAP.items():
        norm_eng, _ = normalize_ingredient_phrase(eng_term)
        cid = canon_lookup.get(norm_eng)
        if cid:
            _add(cid, hindi_word, "hindi_lexicon", 1.0, "VALIDATED")

    # 3. Parenthetical synonyms from recipe corpus
    # Non-ingredient descriptors, preparation words, sizes, and instruction fragments to exclude
    NON_INGREDIENT_DESCRIPTORS = {
        "raw", "ripe", "over ripe", "split", "whole", "fresh", "unsalted", "white",
        "small", "medium", "large", "big", "tender", "optional", "adjust to taste",
        "adjust", "as required", "as needed", "for garnish", "garnish", "taste",
        "chopped", "finely chopped", "sliced", "diced", "grated", "peeled", "crushed",
        "minced", "boiled", "cooked", "roasted", "fried", "washed", "deseeded",
        "shredded", "mashed", "dry", "extra", "thick", "thin", "torn roughly"
    }

    for _, r in ring_df[ring_df["ingredient_id"].notna()].iterrows():
        cid = str(r["ingredient_id"]).strip()
        ing_phrase = str(r.get("ingredient", ""))
        _, parens = extract_parenthetical_info(ing_phrase)
        for p in parens:
            parts = re.split(r"[/,]", p)
            for part in parts:
                part = part.strip()
                p_lower = part.lower()
                if len(part) >= 3 and not any(char.isdigit() for char in part):
                    if p_lower not in NON_INGREDIENT_DESCRIPTORS and len(p_lower.split()) <= 4:
                        _add(cid, part, "parenthetical_synonym", 0.90, "VALIDATED")

    # 4. Recipe ingredients linked mapped phrases
    mapped_ring = ring_df[ring_df["ingredient_id"].notna()][["ingredient", "ingredient_id", "mapping_source"]].drop_duplicates()
    for _, r in mapped_ring.iterrows():
        cid = str(r["ingredient_id"]).strip()
        status = "VALIDATED" if r["mapping_source"] in ("CANONICAL_DATABASE", "VALIDATED_MAPPING") else "AUTO"
        conf = 1.0 if r["mapping_source"] == "CANONICAL_DATABASE" else 0.95
        _add(cid, str(r["ingredient"]), "recipe_corpus", conf, status)

    # 5. Candidate mappings
    for _, r in cand_df.iterrows():
        c_name = str(r["final_canonical_ingredient"]).strip().lower() if pd.notna(r["final_canonical_ingredient"]) else ""
        c_form = str(r["final_ingredient_form"]).strip().lower() if pd.notna(r["final_ingredient_form"]) else "default"
        cid = canon_lookup.get((c_name, c_form)) or canon_lookup.get(c_name)
        if not cid:
            # Check if normalizer resolves to a canonical
            cand_raw = str(r["candidate_ingredient"])
            norm_cand, _ = normalize_ingredient_phrase(cand_raw)
            cid = canon_lookup.get(norm_cand)
            if cid:
                _add(cid, cand_raw, "candidate_auto_normalizer", 0.85, "AUTO")
            continue

        val_status = str(r.get("validation_status", "")).strip().upper()
        if val_status == "VALID":
            status = "VALIDATED"
            conf = 0.95
        elif val_status == "SUSPICIOUS":
            status = "REJECTED"
            conf = 0.0
        else:
            status = "REVIEW_REQUIRED"
            conf = 0.50

        _add(cid, str(r["candidate_ingredient"]), "candidate_corpus", conf, status)

    df = pd.DataFrame(records)
    # Sort for reproducibility
    df = df.sort_values(by=["canonical_ingredient_id", "confidence", "alias"], ascending=[True, False, True]).reset_index(drop=True)
    df["alias_id"] = [f"ALIAS{i+1:05d}" for i in range(len(df))]
    cols = ["alias_id", "canonical_ingredient_id", "alias", "normalized_alias", "source", "confidence", "review_status"]
    return df[cols]


class AliasRegistry:
    """In-memory index for rapid ingredient alias lookups."""

    def __init__(self, alias_df: Optional[pd.DataFrame] = None):
        self._by_normalized_alias: Dict[str, IngredientAlias] = {}
        self._by_exact_alias: Dict[str, IngredientAlias] = {}
        self._by_canonical_id: Dict[str, List[IngredientAlias]] = {}

        if alias_df is not None:
            self.load_from_dataframe(alias_df)

    def load_from_dataframe(self, df: pd.DataFrame) -> None:
        """Load aliases from DataFrame into fast lookup structures."""
        self._by_normalized_alias.clear()
        self._by_exact_alias.clear()
        self._by_canonical_id.clear()

        for _, row in df.iterrows():
            alias = IngredientAlias(
                alias_id=str(row["alias_id"]).strip(),
                canonical_ingredient_id=str(row["canonical_ingredient_id"]).strip(),
                alias=str(row["alias"]).strip(),
                normalized_alias=str(row["normalized_alias"]).strip(),
                source=str(row["source"]).strip(),
                confidence=float(row["confidence"]),
                review_status=str(row["review_status"]).strip(),
            )
            # Only index active / accepted review statuses
            if alias.review_status != "REJECTED":
                self._by_exact_alias[alias.alias.lower()] = alias
                # Prefer higher confidence alias on normalized collision
                existing = self._by_normalized_alias.get(alias.normalized_alias)
                if existing is None or alias.confidence > existing.confidence:
                    self._by_normalized_alias[alias.normalized_alias] = alias

            cid = alias.canonical_ingredient_id
            if cid not in self._by_canonical_id:
                self._by_canonical_id[cid] = []
            self._by_canonical_id[cid].append(alias)

    @classmethod
    def load(cls, file_path: Path = ALIAS_FILE_PATH) -> "AliasRegistry":
        """Load the default alias registry from disk."""
        if not file_path.exists():
            df = compile_ingredient_aliases()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(file_path, index=False)
        else:
            df = pd.read_csv(file_path, low_memory=False)
        return cls(df)

    def lookup(self, term: str) -> Optional[IngredientAlias]:
        """Look up an alias by exact match or normalized match."""
        term_clean = term.strip().lower()
        # 1. Exact match
        if term_clean in self._by_exact_alias:
            return self._by_exact_alias[term_clean]

        # 2. Normalized match
        norm, _ = normalize_ingredient_phrase(term)
        if norm in self._by_normalized_alias:
            return self._by_normalized_alias[norm]

        return None

    def get_aliases_for_id(self, canonical_ingredient_id: str) -> List[IngredientAlias]:
        """Retrieve all aliases for a canonical ingredient ID."""
        return self._by_canonical_id.get(canonical_ingredient_id, [])
