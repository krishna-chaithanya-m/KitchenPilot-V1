"""Validation and structural integrity checker for the Ingredient Ontology."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from src.ingredients.ontology import IngredientOntology


@dataclass
class OntologyValidationReport:
    """Detailed structural integrity report for the ingredient ontology."""

    is_valid: bool
    total_canonical_count: int
    total_alias_count: int
    duplicate_canonical_ids: List[str] = field(default_factory=list)
    empty_canonical_names: List[str] = field(default_factory=list)
    invalid_canonical_ids: List[str] = field(default_factory=list)
    orphan_aliases: List[str] = field(default_factory=list)
    duplicate_alias_ids: List[str] = field(default_factory=list)
    invalid_confidence_values: List[str] = field(default_factory=list)
    invalid_review_statuses: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASS" if self.is_valid else "FAIL"
        err_msg = f", {len(self.errors)} errors" if self.errors else ""
        return (
            f"[{status}] Ontology Validation: {self.total_canonical_count} canonical ingredients, "
            f"{self.total_alias_count} aliases{err_msg}"
        )


def validate_ontology(ontology: IngredientOntology, alias_df: Optional[pd.DataFrame] = None) -> OntologyValidationReport:
    """Validate ontology structural integrity."""
    ingredients = ontology.all_ingredients()
    errors: List[str] = []
    warnings: List[str] = []

    seen_ids: Set[str] = set()
    dup_ids: List[str] = []
    inv_ids: List[str] = []
    empty_names: List[str] = []

    for ing in ingredients:
        cid = ing.ingredient_id
        if cid in seen_ids:
            dup_ids.append(cid)
        seen_ids.add(cid)

        if not re.match(r"^ING\d{5}$", cid):
            inv_ids.append(cid)

        if not ing.canonical_name.strip():
            empty_names.append(f"ID {cid} has empty canonical_name")
        if not ing.display_name.strip():
            empty_names.append(f"ID {cid} has empty display_name")

    if dup_ids:
        errors.append(f"Duplicate canonical IDs found: {dup_ids}")
    if inv_ids:
        errors.append(f"Invalid canonical ID formats: {inv_ids}")
    if empty_names:
        errors.append(f"Empty names found: {empty_names}")

    orphan_aliases: List[str] = []
    dup_alias_ids: List[str] = []
    inv_conf: List[str] = []
    inv_stat: List[str] = []
    total_aliases = 0

    if alias_df is not None:
        total_aliases = len(alias_df)
        seen_alias_ids: Set[str] = set()
        for idx, row in alias_df.iterrows():
            aid = str(row["alias_id"]).strip()
            cid = str(row["canonical_ingredient_id"]).strip()
            conf = float(row["confidence"])
            stat = str(row["review_status"]).strip()

            if aid in seen_alias_ids:
                dup_alias_ids.append(aid)
            seen_alias_ids.add(aid)

            if cid not in seen_ids:
                orphan_aliases.append(f"{aid} references non-existent canonical {cid}")

            if conf < 0.0 or conf > 1.0:
                inv_conf.append(f"{aid} has invalid confidence {conf}")

            if stat not in {"AUTO", "VALIDATED", "REVIEW_REQUIRED", "REJECTED"}:
                inv_stat.append(f"{aid} has invalid review_status '{stat}'")

        if dup_alias_ids:
            errors.append(f"Duplicate alias IDs: {dup_alias_ids[:5]}")
        if orphan_aliases:
            errors.append(f"Orphan aliases: {orphan_aliases[:5]}")
        if inv_conf:
            errors.append(f"Invalid confidence values: {inv_conf[:5]}")
        if inv_stat:
            errors.append(f"Invalid review statuses: {inv_stat[:5]}")

    is_valid = len(errors) == 0
    return OntologyValidationReport(
        is_valid=is_valid,
        total_canonical_count=len(ingredients),
        total_alias_count=total_aliases,
        duplicate_canonical_ids=dup_ids,
        empty_canonical_names=empty_names,
        invalid_canonical_ids=inv_ids,
        orphan_aliases=orphan_aliases,
        duplicate_alias_ids=dup_alias_ids,
        invalid_confidence_values=inv_conf,
        invalid_review_statuses=inv_stat,
        errors=errors,
        warnings=warnings,
    )
