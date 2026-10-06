"""Ingredient Ontology and mapping quality validation script.

Validates structural integrity of the ontology and reports coverage metrics.
Exits non-zero if critical integrity constraints are violated.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
os.chdir(ROOT_DIR)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from src.ingredients.ontology import IngredientOntology
from src.ingredients.validator import validate_ontology


def main() -> int:
    print("=" * 60)
    print("KITCHENPILOT INGREDIENT ONTOLOGY QUALITY AUDIT")
    print("=" * 60)

    # 1. Load datasets
    canonical_file = Path("data/processed/ingredients.csv")
    links_file = Path("data/processed/recipe_ingredients_linked.csv")
    aliases_file = Path("data/mappings/ingredients/ingredient_aliases.csv")
    candidates_file = Path("data/mappings/final_ingredient_mapping_validated.csv")

    for fp in [canonical_file, links_file, aliases_file, candidates_file]:
        if not fp.exists():
            print(f"[FAIL] Required dataset not found: {fp}")
            return 1

    ing_df = pd.read_csv(canonical_file, low_memory=False)
    links_df = pd.read_csv(links_file, low_memory=False)
    alias_df = pd.read_csv(aliases_file, low_memory=False)
    cand_df = pd.read_csv(candidates_file, low_memory=False)

    # 2. Structural Ontology Validation
    ontology = IngredientOntology.load()
    report = validate_ontology(ontology, alias_df)

    print("\n--- Structural Integrity Checks ---")
    print(f"Total Canonical Ingredients : {report.total_canonical_count}")
    print(f"Total Compiled Aliases      : {report.total_alias_count}")
    print(f"Duplicate Canonical IDs     : {len(report.duplicate_canonical_ids)}")
    print(f"Empty Canonical Names       : {len(report.empty_canonical_names)}")
    print(f"Invalid Canonical IDs       : {len(report.invalid_canonical_ids)}")
    print(f"Duplicate Alias IDs         : {len(report.duplicate_alias_ids)}")
    print(f"Orphan Alias References     : {len(report.orphan_aliases)}")
    print(f"Invalid Confidence Values   : {len(report.invalid_confidence_values)}")
    print(f"Invalid Review Statuses     : {len(report.invalid_review_statuses)}")

    if not report.is_valid:
        print("\n[CRITICAL ERRORS DETECTED]")
        for err in report.errors:
            print(f"  - {err}")
        return 1
    else:
        print("  => Structural Integrity: PASS (0 errors)")

    # 3. Recipe Corpus Coverage Audit
    total_raw_strings = len(links_df)
    unique_raw_strings = links_df["original_ingredient"].nunique()
    unique_cleaned_phrases = links_df["ingredient"].nunique()

    mapped_mask = links_df["mapping_status"].isin(["MAPPED_CANONICAL", "MAPPED_VALIDATED"])
    mapped_count = mapped_mask.sum()
    unmapped_count = (~mapped_mask).sum()
    mapped_pct = (mapped_count / max(1, total_raw_strings)) * 100.0

    print("\n--- Recipe Corpus Coverage Audit ---")
    print(f"Total Raw Ingredient Strings: {total_raw_strings:,}")
    print(f"Unique Raw Strings          : {unique_raw_strings:,}")
    print(f"Unique Cleaned Phrases      : {unique_cleaned_phrases:,}")
    print(f"Mapped Recipe Ingredients   : {mapped_count:,} ({mapped_pct:.2f}%)")
    print(f"Unmapped Recipe Ingredients : {unmapped_count:,} ({100.0 - mapped_pct:.2f}%)")
    print(f"Canonical Entities Mapped   : {links_df['ingredient_id'].dropna().nunique()} / {report.total_canonical_count}")

    # 4. Candidate Mapping Pipeline Audit
    total_candidates = len(cand_df)
    unique_candidates = cand_df["candidate_ingredient"].nunique()
    valid_cand = (cand_df["validation_status"] == "VALID").sum()
    suspicious_cand = (cand_df["validation_status"] == "SUSPICIOUS").sum()
    review_cand = (cand_df["validation_status"] == "REVIEW").sum()

    print("\n--- Candidate Mapping Audit ---")
    print(f"Total Candidate Rows        : {total_candidates:,}")
    print(f"Unique Candidates           : {unique_candidates:,}")
    print(f"Validated Candidates (VALID): {valid_cand}")
    print(f"Suspicious / Rejected       : {suspicious_cand}")
    print(f"Review Required             : {review_cand}")

    # 5. Alias Review Breakdown
    alias_status_counts = alias_df["review_status"].value_counts().to_dict()
    print("\n--- Alias Registry Breakdown ---")
    for st, count in sorted(alias_status_counts.items()):
        print(f"  {st:18s}: {count:,}")

    print("\n" + "=" * 60)
    print("ALL INGREDIENT ONTOLOGY INTEGRITY CHECKS PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
