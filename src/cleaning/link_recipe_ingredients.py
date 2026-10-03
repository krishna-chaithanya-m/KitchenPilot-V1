import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


RECIPE_INGREDIENTS_FILE = Path("data/processed/recipe_ingredients.csv")
CANONICAL_INGREDIENTS_FILE = Path("data/processed/ingredients.csv")
VALIDATED_MAPPING_FILE = Path("data/mappings/final_ingredient_mapping_validated.csv")
OUTPUT_FILE = Path("data/processed/recipe_ingredients_linked.csv")

RECIPE_COLUMNS = [
    "recipe_id",
    "original_ingredient",
    "quantity",
    "unit",
    "ingredient",
    "preparation",
]
CANONICAL_COLUMNS = [
    "ingredient_id",
    "canonical_name",
    "display_name",
    "ingredient_form",
    "category",
]
MAPPING_COLUMNS = [
    "candidate_ingredient",
    "cleaned_candidate",
    "normalized_candidate",
    "final_canonical_ingredient",
    "final_ingredient_form",
    "validation_status",
]
LINK_COLUMNS = [
    "ingredient_id",
    "canonical_ingredient",
    "display_name",
    "ingredient_form",
    "category",
    "mapping_status",
    "mapping_source",
]


class IngredientLinkingError(ValueError):
    """Raised when linking inputs or generated output fail validation."""


def normalize_ingredient(value: Any) -> str:
    """Apply the candidate-generation normalization to an ingredient value."""
    if pd.isna(value):
        return ""

    text = str(value).strip().lower()
    text = re.sub(r"\s*\([^)]*\)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .")


def _require_columns(
    dataframe: pd.DataFrame, required: list[str], source_name: str
) -> None:
    missing = [column for column in required if column not in dataframe.columns]
    if missing:
        raise IngredientLinkingError(
            f"{source_name} is missing required column(s): {', '.join(missing)}"
        )


def _canonical_record(row: dict[str, str]) -> dict[str, str]:
    return {
        "ingredient_id": row["ingredient_id"].strip(),
        "canonical_ingredient": row["canonical_name"].strip(),
        "display_name": row["display_name"].strip(),
        "ingredient_form": row["ingredient_form"].strip(),
        "category": row["category"].strip(),
    }


def _build_canonical_lookups(
    canonical_df: pd.DataFrame,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, dict[str, str]]],
]:
    alias_choices: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    canonical_choices: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    seen_ids: set[str] = set()

    for row in canonical_df[CANONICAL_COLUMNS].to_dict(orient="records"):
        record = _canonical_record(row)
        ingredient_id = record["ingredient_id"]
        if not ingredient_id:
            raise IngredientLinkingError(
                "Canonical ingredient has a blank ingredient_id"
            )
        if ingredient_id in seen_ids:
            raise IngredientLinkingError(
                f"Duplicate canonical ingredient_id in ingredients.csv: {ingredient_id}"
            )
        seen_ids.add(ingredient_id)

        canonical_key = normalize_ingredient(row["canonical_name"])
        if not canonical_key:
            raise IngredientLinkingError(
                f"Canonical ingredient {ingredient_id} has a blank canonical_name"
            )
        canonical_choices[canonical_key][ingredient_id] = record

        for name in (row["canonical_name"], row["display_name"]):
            key = normalize_ingredient(name)
            if not key:
                continue
            alias_choices[key][ingredient_id] = record

    # Ambiguous aliases are omitted so those recipe records remain available for review.
    by_name = {
        key: next(iter(records.values()))
        for key, records in alias_choices.items()
        if len(records) == 1
    }
    return by_name, canonical_choices


def _build_validated_lookup(
    mapping_df: pd.DataFrame,
    canonical_by_name: dict[str, dict[str, dict[str, str]]],
) -> tuple[dict[str, dict[str, str]], dict[str, set[str]]]:
    valid_mask = (
        mapping_df["validation_status"]
        .astype(str)
        .str.strip()
        .str.casefold()
        .eq("valid")
    )
    valid_mapping = mapping_df.loc[valid_mask]
    choices: dict[str, dict[tuple[str, str], dict[str, str]]] = defaultdict(dict)
    valid_target_ids: dict[str, set[str]] = defaultdict(set)

    for row in valid_mapping.to_dict(orient="records"):
        target_key = normalize_ingredient(row["final_canonical_ingredient"])
        if not target_key:
            raise IngredientLinkingError(
                "A VALID mapping row has a blank final_canonical_ingredient"
            )
        canonical_options = list(canonical_by_name.get(target_key, {}).values())
        mapped_form = str(row["final_ingredient_form"]).strip()
        if mapped_form:
            form_key = normalize_ingredient(mapped_form)
            canonical_options = [
                record
                for record in canonical_options
                if normalize_ingredient(record["ingredient_form"]) == form_key
            ]
        if len(canonical_options) != 1:
            raise IngredientLinkingError(
                "A VALID mapping target does not resolve to exactly one canonical "
                "ingredient/form in ingredients.csv: "
                f"{row['final_canonical_ingredient']!r} ({mapped_form or 'no form'})"
            )

        record = canonical_options[0].copy()
        if mapped_form:
            record["ingredient_form"] = mapped_form

        signature = (record["ingredient_id"], record["ingredient_form"])
        for column in (
            "candidate_ingredient",
            "cleaned_candidate",
            "normalized_candidate",
        ):
            key = normalize_ingredient(row[column])
            if key:
                choices[key][signature] = record
                valid_target_ids[key].add(record["ingredient_id"])

    # Aliases that lead to conflicting canonical ingredients/forms are not safe to use.
    unambiguous = {
        key: next(iter(records.values()))
        for key, records in choices.items()
        if len(records) == 1
    }
    return unambiguous, valid_target_ids


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = (
        RECIPE_INGREDIENTS_FILE,
        CANONICAL_INGREDIENTS_FILE,
        VALIDATED_MAPPING_FILE,
    )
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Required input file(s) not found: " + ", ".join(missing)
        )

    read_options = {"dtype": str, "keep_default_na": False, "encoding": "utf-8-sig"}
    recipe_df = pd.read_csv(RECIPE_INGREDIENTS_FILE, **read_options)
    canonical_df = pd.read_csv(CANONICAL_INGREDIENTS_FILE, **read_options)
    mapping_df = pd.read_csv(VALIDATED_MAPPING_FILE, **read_options)

    _require_columns(recipe_df, RECIPE_COLUMNS, str(RECIPE_INGREDIENTS_FILE))
    _require_columns(canonical_df, CANONICAL_COLUMNS, str(CANONICAL_INGREDIENTS_FILE))
    _require_columns(mapping_df, MAPPING_COLUMNS, str(VALIDATED_MAPPING_FILE))
    return recipe_df, canonical_df, mapping_df


def link_recipe_ingredients(
    recipe_df: pd.DataFrame,
    canonical_df: pd.DataFrame,
    mapping_df: pd.DataFrame,
) -> pd.DataFrame:
    """Link each parsed ingredient to a canonical ingredient when deterministic."""
    _require_columns(recipe_df, RECIPE_COLUMNS, "Recipe ingredients")
    _require_columns(canonical_df, CANONICAL_COLUMNS, "Canonical ingredients")
    _require_columns(mapping_df, MAPPING_COLUMNS, "Validated mappings")

    canonical_by_name, canonical_by_canonical_name = _build_canonical_lookups(
        canonical_df
    )
    validated_by_candidate, _ = _build_validated_lookup(
        mapping_df, canonical_by_canonical_name
    )

    linked_records: list[dict[str, str]] = []
    for row in recipe_df.to_dict(orient="records"):
        key = normalize_ingredient(row["ingredient"])
        canonical_record = canonical_by_name.get(key) if key else None
        if canonical_record is not None:
            match = canonical_record.copy()
            match["mapping_status"] = "MAPPED_CANONICAL"
            match["mapping_source"] = "CANONICAL_DATABASE"
        else:
            match = validated_by_candidate.get(key) if key else None
            if match is not None:
                match = match.copy()
                match["mapping_status"] = "MAPPED_VALIDATED"
                match["mapping_source"] = "VALIDATED_MAPPING"
            else:
                match = {
                    "ingredient_id": "",
                    "canonical_ingredient": "",
                    "display_name": "",
                    "ingredient_form": "",
                    "category": "",
                    "mapping_status": "REVIEW",
                    "mapping_source": "NONE",
                }

        linked_records.append({**row, **match})

    output_columns = list(recipe_df.columns) + [
        column for column in LINK_COLUMNS if column not in recipe_df.columns
    ]
    return pd.DataFrame(linked_records, columns=output_columns)


def validate_linked_output(
    recipe_df: pd.DataFrame,
    linked_df: pd.DataFrame,
    canonical_df: pd.DataFrame,
    mapping_df: pd.DataFrame,
) -> None:
    """Raise an error if any linking invariant is violated."""
    if len(linked_df) != len(recipe_df):
        raise IngredientLinkingError(
            f"Output row count ({len(linked_df)}) does not match input "
            f"({len(recipe_df)}); no rows may be dropped."
        )

    for column in recipe_df.columns:
        if not linked_df[column].equals(recipe_df[column]):
            raise IngredientLinkingError(
                f"Original input column was changed during linking: {column}"
            )

    canonical_ids = set(canonical_df["ingredient_id"].astype(str))
    populated_ids = set(
        linked_df.loc[linked_df["ingredient_id"] != "", "ingredient_id"]
    )
    unknown_ids = populated_ids - canonical_ids
    if unknown_ids:
        raise IngredientLinkingError(
            "Output contains ingredient_id value(s) absent from ingredients.csv: "
            + ", ".join(sorted(unknown_ids))
        )

    allowed_statuses = {"MAPPED_CANONICAL", "MAPPED_VALIDATED", "REVIEW"}
    unexpected_statuses = set(linked_df["mapping_status"]) - allowed_statuses
    if unexpected_statuses:
        raise IngredientLinkingError(
            "Unexpected mapping_status value(s): "
            + ", ".join(sorted(unexpected_statuses))
        )

    canonical_rows = linked_df[linked_df["mapping_status"] == "MAPPED_CANONICAL"]
    if not canonical_rows["mapping_source"].eq("CANONICAL_DATABASE").all():
        raise IngredientLinkingError("Canonical matches have an invalid mapping_source")

    validated_rows = linked_df[linked_df["mapping_status"] == "MAPPED_VALIDATED"]
    if not validated_rows["mapping_source"].eq("VALIDATED_MAPPING").all():
        raise IngredientLinkingError("Validated matches have an invalid mapping_source")

    _, canonical_by_canonical_name = _build_canonical_lookups(canonical_df)
    _, valid_target_ids = _build_validated_lookup(
        mapping_df, canonical_by_canonical_name
    )
    for row in validated_rows.to_dict(orient="records"):
        key = normalize_ingredient(row["ingredient"])
        if row["ingredient_id"] not in valid_target_ids.get(key, set()):
            raise IngredientLinkingError(
                "MAPPED_VALIDATED row does not resolve through a VALID mapping: "
                f"{row['ingredient']!r}"
            )

    review_rows = linked_df[linked_df["mapping_status"] == "REVIEW"]
    review_sources = review_rows["mapping_source"].eq("NONE")
    review_fields_blank = (
        review_rows[
            [
                "ingredient_id",
                "canonical_ingredient",
                "display_name",
                "ingredient_form",
                "category",
            ]
        ]
        .eq("")
        .all(axis=1)
    )
    if not (review_sources & review_fields_blank).all():
        raise IngredientLinkingError(
            "REVIEW rows must have blank canonical fields and source NONE"
        )


def print_summary(linked_df: pd.DataFrame) -> None:
    total = len(linked_df)
    status_counts = linked_df["mapping_status"].value_counts()
    mapped = total - int(status_counts.get("REVIEW", 0))
    percentage = (mapped / total * 100) if total else 0.0
    mapped_ingredient_ids = linked_df.loc[
        linked_df["mapping_status"] != "REVIEW", "ingredient_id"
    ].nunique()
    unmapped = linked_df.loc[linked_df["mapping_status"] == "REVIEW", "ingredient"]
    unmapped_counts = Counter(
        key for value in unmapped if (key := normalize_ingredient(value))
    )

    print("=" * 50)
    print("RECIPE INGREDIENT LINKING")
    print("=" * 50)
    print(f"\nTotal ingredient records: {total}")
    print(f"\nMapped: {mapped}")
    print(f"Review: {int(status_counts.get('REVIEW', 0))}")
    print(f"\nMapping percentage: {percentage:.2f}%")
    print("\nBy mapping status:")
    for status in ("MAPPED_CANONICAL", "MAPPED_VALIDATED", "REVIEW"):
        print(f"{status:<20} {int(status_counts.get(status, 0))}")
    print(f"\nUnique mapped ingredients: {mapped_ingredient_ids}")
    print(f"Unique unmapped ingredient strings: {len(unmapped_counts)}")
    print("\nTop 20 unmapped ingredient strings by frequency:")
    if unmapped_counts:
        for ingredient, count in unmapped_counts.most_common(20):
            print(f"{count:>6}  {ingredient}")
    else:
        print("No unmapped ingredients.")
    print(f"\nOutput:\n{OUTPUT_FILE}")


def main() -> None:
    recipe_df, canonical_df, mapping_df = _load_inputs()
    linked_df = link_recipe_ingredients(recipe_df, canonical_df, mapping_df)
    validate_linked_output(recipe_df, linked_df, canonical_df, mapping_df)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    linked_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    print_summary(linked_df)


if __name__ == "__main__":
    main()
