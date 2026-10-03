"""Validate the review-only KitchenPilot-to-CNF candidate table."""

import hashlib
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cleaning.match_ingredients_to_cnf import (  # noqa: E402
    INGREDIENTS_FILE,
    CNF_FILE,
    VALIDATED_MAPPING_FILE,
    LINKED_RECIPE_INGREDIENTS_FILE,
    OUTPUT_FILE,
    _load_inputs,
    generate_candidates,
)

RECIPES_FILE = Path("data/processed/recipes.csv")

REQUIRED_COLUMNS = [
    "ingredient_id",
    "canonical_name",
    "display_name",
    "ingredient_form",
    "category",
    "cnf_food_code",
    "cnf_food_name",
    "cnf_food_description",
    "cnf_alternate_description",
    "cnf_food_form",
    "match_method",
    "match_score",
    "candidate_rank",
    "selection_status",
    "review_notes",
    "matched_term",
    "cnf_food_source_code",
    "source_usda_ndb_code",
    "source_reference",
    "cnf_food_last_updated_date",
    "recipe_form_evidence",
]
ALLOWED_STATUSES = {"AUTO_CANDIDATE", "REVIEW", "NO_MATCH"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")
    return pd.read_csv(
        path,
        dtype="string",
        keep_default_na=False,
        encoding="utf-8-sig",
        low_memory=False,
    )


def _canonicalize_for_compare(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.fillna("").astype("string").reset_index(drop=True)


def validate() -> dict[str, int]:
    protected_paths = [
        INGREDIENTS_FILE,
        LINKED_RECIPE_INGREDIENTS_FILE,
        RECIPES_FILE,
        CNF_FILE,
        VALIDATED_MAPPING_FILE,
    ]
    before_hashes = {path: _sha256(path) for path in protected_paths}

    ingredients, cnf_rows, mappings, recipe_evidence = _load_inputs()
    candidates = _read_csv(OUTPUT_FILE)
    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in candidates
    ]
    if missing_columns:
        raise ValueError(
            "Review mapping is missing required column(s): "
            + ", ".join(missing_columns)
        )

    ingredient_ids = set(ingredients["ingredient_id"])
    candidate_ingredient_ids = set(candidates["ingredient_id"])
    if candidate_ingredient_ids != ingredient_ids:
        missing = sorted(ingredient_ids - candidate_ingredient_ids)
        extra = sorted(candidate_ingredient_ids - ingredient_ids)
        raise ValueError(
            f"Ingredient review coverage mismatch; missing={missing}, extra={extra}"
        )

    cnf_food_ids = set(cnf_rows["source_food_id"])
    matched = candidates[candidates["cnf_food_code"] != ""]
    unknown_food_ids = set(matched["cnf_food_code"]) - cnf_food_ids
    if unknown_food_ids:
        raise ValueError(
            "Review mapping references nonexistent CNF food code(s): "
            + ", ".join(sorted(unknown_food_ids)[:20])
        )

    unexpected_statuses = set(candidates["selection_status"]) - ALLOWED_STATUSES
    if unexpected_statuses:
        raise ValueError(
            "Review mapping has unexpected selection status value(s): "
            + ", ".join(sorted(unexpected_statuses))
        )

    no_match = candidates[candidates["selection_status"] == "NO_MATCH"]
    if no_match["cnf_food_code"].ne("").any():
        raise ValueError("NO_MATCH rows must not reference a CNF food code")
    if not no_match["match_method"].eq("NO_MATCH").all():
        raise ValueError("NO_MATCH rows must have match_method=NO_MATCH")
    if not no_match["cnf_food_form"].eq("").all():
        raise ValueError("NO_MATCH rows must have a blank CNF form")

    ranks = pd.to_numeric(candidates["candidate_rank"], errors="coerce")
    if ranks.isna().any() or (ranks < 1).any():
        raise ValueError("Candidate ranks must be positive integers")
    if not ranks.eq(ranks.astype(int)).all():
        raise ValueError("Candidate ranks must be integers")
    ranked = candidates.assign(_rank=ranks.astype(int))
    for ingredient_id, group in ranked.groupby("ingredient_id", sort=False):
        actual = sorted(group["_rank"].tolist())
        expected = list(range(1, len(group) + 1))
        if actual != expected:
            raise ValueError(
                f"Candidate ranks for {ingredient_id} are not contiguous from 1: {actual}"
            )

    if candidates.duplicated(
        ["ingredient_id", "cnf_food_code", "candidate_rank"]
    ).any():
        raise ValueError("Duplicate ingredient/candidate/rank rows were found")

    if candidates.loc[matched.index, "cnf_food_name"].eq("").any():
        raise ValueError("A referenced CNF food code has no food name")
    cnf_by_id = cnf_rows.drop_duplicates("source_food_id").set_index("source_food_id")
    expected_names = matched["cnf_food_code"].map(cnf_by_id["food_name"])
    if not expected_names.reset_index(drop=True).equals(
        matched["cnf_food_name"].reset_index(drop=True)
    ):
        raise ValueError("CNF food names were changed or merged in the review output")

    # CNF-derived form tags must remain attached to their original food codes.
    expected_forms = matched["cnf_food_code"].map(cnf_by_id["food_form"])
    for source_form, candidate_form in zip(expected_forms, matched["cnf_food_form"]):
        source_tags = {
            tag
            for tag in str(source_form).split(";")
            if tag and tag != "unspecified_in_description"
        }
        output_tags = set(str(candidate_form).split(";"))
        if not source_tags.issubset(output_tags):
            raise ValueError(
                "A CNF food-form distinction was lost for food code "
                f"{matched.iloc[0]['cnf_food_code']}"
            )

    if (
        candidates["selection_status"].eq("AUTO_CANDIDATE").any()
        and candidates["selection_status"].eq("MAPPED").any()
    ):
        raise ValueError("Candidate generation must not create final approved mappings")

    expected = generate_candidates(ingredients, cnf_rows, mappings, recipe_evidence)
    if list(expected.columns) != list(candidates.columns):
        raise ValueError("Regenerated candidate schema differs from saved review table")
    if not _canonicalize_for_compare(expected).equals(
        _canonicalize_for_compare(candidates)
    ):
        raise ValueError("Candidate ranks/results are not deterministic")

    changed_paths = [
        str(path) for path in protected_paths if _sha256(path) != before_hashes[path]
    ]
    if changed_paths:
        raise ValueError(
            "Existing project/source inputs changed during validation: "
            + ", ".join(changed_paths)
        )

    statuses = candidates["selection_status"].value_counts()
    return {
        "ingredients": len(ingredients),
        "candidate_rows": len(candidates),
        "matched_rows": len(matched),
        "auto_candidates": int(statuses.get("AUTO_CANDIDATE", 0)),
        "review_rows": int(statuses.get("REVIEW", 0)),
        "no_match_ingredients": int(statuses.get("NO_MATCH", 0)),
    }


def main() -> None:
    stats = validate()
    print("=" * 50)
    print("CNF INGREDIENT MAPPING VALIDATION")
    print("=" * 50)
    print("\nKitchenPilot coverage: PASS")
    print("CNF food IDs: PASS")
    print("Candidate ranks: PASS")
    print("Food forms preserved: PASS")
    print("Review-only statuses: PASS")
    print("Existing inputs unchanged: PASS")
    print("Deterministic ranking: PASS")
    print("\nValidation result: PASS")
    print(
        f"\nIngredients: {stats['ingredients']}; candidate rows: {stats['candidate_rows']}; "
        f"matched rows: {stats['matched_rows']}"
    )
    print(
        f"AUTO_CANDIDATE: {stats['auto_candidates']}; REVIEW: {stats['review_rows']}; "
        f"NO_MATCH ingredients: {stats['no_match_ingredients']}"
    )
    print(f"\nValidated output:\n{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
