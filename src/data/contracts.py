"""Production data contracts and validation engine for KitchenPilot datasets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd
from pydantic import ValidationError

from src.data.schemas import (
    CanonicalIngredientSchema,
    IngredientAliasSchema,
    RecipeIngredientLinkedSchema,
    RecipeIngredientNutritionSchema,
    RecipeNutritionSchema,
    RecipeSchema,
)


@dataclass
class ValidationResult:
    """Structured report of dataset contract validation."""

    dataset_name: str
    is_valid: bool
    total_records: int
    valid_records: int
    invalid_records: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    invalid_sample: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASS" if self.is_valid else "FAIL"
        err_str = f", {len(self.errors)} errors" if self.errors else ""
        warn_str = f", {len(self.warnings)} warnings" if self.warnings else ""
        return (
            f"[{status}] {self.dataset_name}: {self.valid_records}/{self.total_records} "
            f"valid records ({self.valid_records/max(1, self.total_records)*100:.1f}%){err_str}{warn_str}"
        )


def _check_required_columns(df: pd.DataFrame, required: List[str], dataset_name: str) -> List[str]:
    missing = [c for c in required if c not in df.columns]
    if missing:
        return [f"{dataset_name} missing required columns: {', '.join(missing)}"]
    return []


def validate_recipe_dataset(df: pd.DataFrame) -> ValidationResult:
    """Validate recipes.csv against the production Recipe contract."""
    name = "recipes.csv"
    required_cols = [
        "recipe_id", "recipe_name", "cuisine", "meal_type", "category",
        "prep_time_min", "cook_time_min", "total_time_min", "servings",
        "vegetarian", "vegan", "jain", "satvik", "source_id", "source_license"
    ]
    col_errors = _check_required_columns(df, required_cols, name)
    if col_errors:
        return ValidationResult(name, False, len(df), 0, len(df), errors=col_errors)

    errors: List[str] = []
    warnings: List[str] = []
    invalid_samples: List[Dict[str, Any]] = []

    # Uniqueness check
    dup_ids = df[df["recipe_id"].duplicated()]["recipe_id"].tolist()
    if dup_ids:
        errors.append(f"Duplicate recipe_id values found: {dup_ids[:5]} (total {len(dup_ids)})")

    # Null recipe_names
    null_names = df["recipe_name"].isna().sum()
    if null_names > 0:
        errors.append(f"{null_names} recipes have null recipe_name")

    # Time sanity
    neg_times = (df["prep_time_min"] < 0) | (df["cook_time_min"] < 0) | (df["total_time_min"] < 0)
    if neg_times.sum() > 0:
        errors.append(f"{neg_times.sum()} recipes have negative time values")

    # Servings sanity
    invalid_servings = (df["servings"] < 1) | df["servings"].isna()
    if invalid_servings.sum() > 0:
        errors.append(f"{invalid_servings.sum()} recipes have invalid servings (< 1 or null)")

    # Recipes with null ingredients text
    null_ing = df["ingredients"].isna().sum()
    if null_ing > 0:
        warnings.append(f"{null_ing} recipes have null ingredients text in source corpus")

    # Sample Pydantic model validation on up to 500 rows for deep contract enforcement
    sample_size = min(500, len(df))
    sample_df = df.sample(sample_size, random_state=42) if len(df) > sample_size else df
    schema_failures = 0
    for idx, row in sample_df.iterrows():
        try:
            RecipeSchema(**row.to_dict())
        except ValidationError as e:
            schema_failures += 1
            if len(invalid_samples) < 5:
                invalid_samples.append({"index": idx, "recipe_id": row.get("recipe_id"), "error": str(e)})

    if schema_failures > 0:
        errors.append(f"Pydantic schema validation failed on {schema_failures}/{sample_size} sampled records")

    is_valid = len(errors) == 0
    valid_count = len(df) if is_valid else max(0, len(df) - len(dup_ids) - schema_failures)

    return ValidationResult(
        dataset_name=name,
        is_valid=is_valid,
        total_records=len(df),
        valid_records=valid_count,
        invalid_records=len(df) - valid_count,
        errors=errors,
        warnings=warnings,
        invalid_sample=invalid_samples,
    )


def validate_ingredient_dataset(df: pd.DataFrame) -> ValidationResult:
    """Validate ingredients.csv against the Canonical Ingredient contract."""
    name = "ingredients.csv"
    required_cols = [
        "ingredient_id", "canonical_name", "display_name", "ingredient_form",
        "category", "recipe_occurrence_count", "candidate_variant_count", "source", "mapping_status"
    ]
    col_errors = _check_required_columns(df, required_cols, name)
    if col_errors:
        return ValidationResult(name, False, len(df), 0, len(df), errors=col_errors)

    errors: List[str] = []
    warnings: List[str] = []
    invalid_samples: List[Dict[str, Any]] = []

    # Uniqueness check on ingredient_id
    dup_ids = df[df["ingredient_id"].duplicated()]["ingredient_id"].tolist()
    if dup_ids:
        errors.append(f"Duplicate ingredient_id values found: {dup_ids}")

    # Format check on ingredient_id
    invalid_ids = df[~df["ingredient_id"].astype(str).str.match(r"^ING\d{5}$")]["ingredient_id"].tolist()
    if invalid_ids:
        errors.append(f"Invalid ingredient_id format: {invalid_ids}")

    # Check for empty canonical_name or display_name
    empty_names = df["canonical_name"].isna() | (df["canonical_name"].astype(str).str.strip() == "")
    if empty_names.sum() > 0:
        errors.append(f"{empty_names.sum()} canonical ingredients have empty canonical_name")

    empty_disp = df["display_name"].isna() | (df["display_name"].astype(str).str.strip() == "")
    if empty_disp.sum() > 0:
        errors.append(f"{empty_disp.sum()} canonical ingredients have empty display_name")

    # Complete schema check for all rows (small dataset: 128 rows)
    for idx, row in df.iterrows():
        try:
            CanonicalIngredientSchema(**row.to_dict())
        except ValidationError as e:
            errors.append(f"Row {idx} ({row.get('ingredient_id')}): {e}")
            if len(invalid_samples) < 5:
                invalid_samples.append({"row": idx, "id": row.get("ingredient_id"), "error": str(e)})

    is_valid = len(errors) == 0
    valid_count = len(df) if is_valid else max(0, len(df) - len(errors))

    return ValidationResult(
        dataset_name=name,
        is_valid=is_valid,
        total_records=len(df),
        valid_records=valid_count,
        invalid_records=len(df) - valid_count,
        errors=errors,
        warnings=warnings,
        invalid_sample=invalid_samples,
    )


def validate_recipe_ingredient_links(df: pd.DataFrame) -> ValidationResult:
    """Validate recipe_ingredients_linked.csv against the Link contract."""
    name = "recipe_ingredients_linked.csv"
    required_cols = [
        "recipe_id", "original_ingredient", "quantity", "unit", "ingredient",
        "preparation", "ingredient_id", "canonical_ingredient", "mapping_status", "mapping_source"
    ]
    col_errors = _check_required_columns(df, required_cols, name)
    if col_errors:
        return ValidationResult(name, False, len(df), 0, len(df), errors=col_errors)

    errors: List[str] = []
    warnings: List[str] = []
    invalid_samples: List[Dict[str, Any]] = []

    # Empty original ingredient text
    empty_orig = df["original_ingredient"].isna() | (df["original_ingredient"].astype(str).str.strip() == "")
    if empty_orig.sum() > 0:
        errors.append(f"{empty_orig.sum()} records have empty original_ingredient text")

    # Mapping status consistency: mapped rows must have ingredient_id
    mapped_mask = df["mapping_status"].isin(["MAPPED_CANONICAL", "MAPPED_VALIDATED"])
    missing_id_in_mapped = mapped_mask & (df["ingredient_id"].isna() | (df["ingredient_id"].astype(str).str.strip() == ""))
    if missing_id_in_mapped.sum() > 0:
        errors.append(f"{missing_id_in_mapped.sum()} mapped records lack an ingredient_id")

    # Review status consistency: review rows must NOT have valid mapped ID
    review_mask = df["mapping_status"] == "REVIEW"
    has_id_in_review = review_mask & df["ingredient_id"].notna() & (df["ingredient_id"].astype(str).str.strip() != "")
    if has_id_in_review.sum() > 0:
        warnings.append(f"{has_id_in_review.sum()} REVIEW records unexpectedly have an ingredient_id")

    mapped_pct = mapped_mask.sum() / max(1, len(df)) * 100
    if mapped_pct < 70.0:
        warnings.append(f"Low overall mapped percentage: {mapped_pct:.1f}%")

    is_valid = len(errors) == 0
    valid_count = len(df) if is_valid else max(0, len(df) - missing_id_in_mapped.sum() - empty_orig.sum())

    return ValidationResult(
        dataset_name=name,
        is_valid=is_valid,
        total_records=len(df),
        valid_records=valid_count,
        invalid_records=len(df) - valid_count,
        errors=errors,
        warnings=warnings,
        invalid_sample=invalid_samples,
    )


def validate_recipe_nutrition_dataset(df: pd.DataFrame) -> ValidationResult:
    """Validate recipe_nutrition.csv against the Nutrition contract."""
    name = "recipe_nutrition.csv"
    required_cols = [
        "recipe_id", "recipe_name", "servings", "total_calories_kcal",
        "total_protein_g", "total_fat_g", "total_carbs_g", "total_fiber_g",
        "per_serving_calories_kcal", "nutrition_quality"
    ]
    col_errors = _check_required_columns(df, required_cols, name)
    if col_errors:
        return ValidationResult(name, False, len(df), 0, len(df), errors=col_errors)

    errors: List[str] = []
    warnings: List[str] = []
    invalid_samples: List[Dict[str, Any]] = []

    # Duplicate recipe_id
    dup_ids = df[df["recipe_id"].duplicated()]["recipe_id"].tolist()
    if dup_ids:
        errors.append(f"Duplicate recipe_id in nutrition dataset: {dup_ids[:5]}")

    # Negative nutrition values
    nut_cols = [
        "total_calories_kcal", "total_protein_g", "total_fat_g", "total_carbs_g",
        "total_fiber_g", "per_serving_calories_kcal", "per_serving_protein_g"
    ]
    for c in nut_cols:
        if c in df.columns:
            neg_count = (df[c] < 0).sum()
            if neg_count > 0:
                errors.append(f"Negative values found in nutrition column '{c}': {neg_count} rows")

    # Quality distribution
    quality_counts = df["nutrition_quality"].value_counts().to_dict()
    allowed_qualities = {"COMPLETE", "PARTIAL", "APPROXIMATE"}
    invalid_q = set(quality_counts.keys()) - allowed_qualities
    if invalid_q:
        errors.append(f"Invalid nutrition_quality categories: {invalid_q}")

    # Check zero calorie recipes
    zero_cal = (df["total_calories_kcal"] == 0).sum()
    if zero_cal > 0:
        warnings.append(f"{zero_cal} recipes have 0.0 total calories")

    is_valid = len(errors) == 0
    valid_count = len(df) if is_valid else max(0, len(df) - len(dup_ids))

    return ValidationResult(
        dataset_name=name,
        is_valid=is_valid,
        total_records=len(df),
        valid_records=valid_count,
        invalid_records=len(df) - valid_count,
        errors=errors,
        warnings=warnings,
        invalid_sample=invalid_samples,
    )


def validate_recipe_ingredient_nutrition_dataset(df: pd.DataFrame) -> ValidationResult:
    """Validate recipe_ingredient_nutrition.csv against the Per-Ingredient Nutrition contract."""
    name = "recipe_ingredient_nutrition.csv"
    required_cols = [
        "recipe_id", "original_ingredient", "ingredient", "energy_kcal",
        "protein_g", "fat_g", "carbs_g", "fiber_g", "sodium_mg",
        "mapping_quality", "nutrition_quality", "nutrition_source"
    ]
    col_errors = _check_required_columns(df, required_cols, name)
    if col_errors:
        return ValidationResult(name, False, len(df), 0, len(df), errors=col_errors)

    errors: List[str] = []
    warnings: List[str] = []

    # Negative nutrition values
    for c in ["energy_kcal", "protein_g", "fat_g", "carbs_g", "fiber_g", "sodium_mg"]:
        neg = (df[c] < 0).sum()
        if neg > 0:
            errors.append(f"Negative values in '{c}': {neg} rows")

    is_valid = len(errors) == 0
    return ValidationResult(
        dataset_name=name,
        is_valid=is_valid,
        total_records=len(df),
        valid_records=len(df) if is_valid else 0,
        invalid_records=0 if is_valid else len(df),
        errors=errors,
        warnings=warnings,
    )


def validate_ingredient_aliases_dataset(df: pd.DataFrame) -> ValidationResult:
    """Validate data/mappings/ingredients/ingredient_aliases.csv."""
    name = "ingredient_aliases.csv"
    required_cols = [
        "alias_id", "canonical_ingredient_id", "alias", "normalized_alias",
        "source", "confidence", "review_status"
    ]
    col_errors = _check_required_columns(df, required_cols, name)
    if col_errors:
        return ValidationResult(name, False, len(df), 0, len(df), errors=col_errors)

    errors: List[str] = []
    warnings: List[str] = []

    # Uniqueness check on alias_id
    dup_ids = df[df["alias_id"].duplicated()]["alias_id"].tolist()
    if dup_ids:
        errors.append(f"Duplicate alias_id: {dup_ids[:5]}")

    # Format checks
    inv_aid = df[~df["alias_id"].astype(str).str.match(r"^ALIAS\d{5}$")]["alias_id"].tolist()
    if inv_aid:
        errors.append(f"Invalid alias_id format: {inv_aid[:5]}")

    inv_cid = df[~df["canonical_ingredient_id"].astype(str).str.match(r"^ING\d{5}$")]["canonical_ingredient_id"].tolist()
    if inv_cid:
        errors.append(f"Invalid canonical_ingredient_id in alias: {inv_cid[:5]}")

    # Confidence range
    inv_conf = (df["confidence"] < 0.0) | (df["confidence"] > 1.0)
    if inv_conf.sum() > 0:
        errors.append(f"{inv_conf.sum()} aliases have confidence outside [0.0, 1.0]")

    # Review status values
    allowed_statuses = {"AUTO", "VALIDATED", "REVIEW_REQUIRED", "REJECTED"}
    bad_statuses = set(df["review_status"].unique()) - allowed_statuses
    if bad_statuses:
        errors.append(f"Invalid review_status values: {bad_statuses}")

    is_valid = len(errors) == 0
    return ValidationResult(
        dataset_name=name,
        is_valid=is_valid,
        total_records=len(df),
        valid_records=len(df) if is_valid else 0,
        invalid_records=0 if is_valid else len(df),
        errors=errors,
        warnings=warnings,
    )


def validate_cross_dataset_integrity(
    recipes_df: pd.DataFrame,
    nutrition_df: pd.DataFrame,
    ingredients_df: pd.DataFrame,
    links_df: pd.DataFrame,
    aliases_df: Optional[pd.DataFrame] = None,
) -> ValidationResult:
    """Validate referential integrity across the entire relational production dataset."""
    name = "Cross-Dataset Referential Integrity"
    errors: List[str] = []
    warnings: List[str] = []

    recipe_ids: Set[str] = set(recipes_df["recipe_id"].dropna().unique())
    nutrition_recipe_ids: Set[str] = set(nutrition_df["recipe_id"].dropna().unique())
    ingredient_ids: Set[str] = set(ingredients_df["ingredient_id"].dropna().unique())

    # 1. Nutrition -> Recipe foreign key
    orphan_nutrition = nutrition_recipe_ids - recipe_ids
    if orphan_nutrition:
        errors.append(f"{len(orphan_nutrition)} orphan nutrition records reference non-existent recipes")

    missing_nutrition = recipe_ids - nutrition_recipe_ids
    if missing_nutrition:
        errors.append(f"{len(missing_nutrition)} recipes have no matching nutrition record")

    # 2. Recipe Ingredient Links -> Recipe foreign key
    link_recipe_ids: Set[str] = set(links_df["recipe_id"].dropna().unique())
    orphan_links = link_recipe_ids - recipe_ids
    if orphan_links:
        errors.append(f"{len(orphan_links)} link records reference non-existent recipes")

    missing_links = recipe_ids - link_recipe_ids
    if missing_links:
        warnings.append(
            f"{len(missing_links)} recipes have no parsed ingredient links (empty in source corpus: {sorted(list(missing_links))})"
        )

    # 3. Recipe Ingredient Links -> Canonical Ingredient foreign key
    mapped_links = links_df[links_df["ingredient_id"].notna()]
    mapped_ing_ids: Set[str] = set(mapped_links["ingredient_id"].astype(str).str.strip().unique()) - {""}
    orphan_ingredient_links = mapped_ing_ids - ingredient_ids
    if orphan_ingredient_links:
        errors.append(f"{len(orphan_ingredient_links)} links reference non-existent canonical ingredients: {orphan_ingredient_links}")

    # 4. Canonical Ingredient coverage in recipe corpus
    unused_ingredients = ingredient_ids - mapped_ing_ids
    if unused_ingredients:
        warnings.append(f"{len(unused_ingredients)} canonical ingredients are not currently referenced in recipe links: {unused_ingredients}")

    # 5. Aliases -> Canonical Ingredient foreign key
    if aliases_df is not None:
        alias_ing_ids = set(aliases_df["canonical_ingredient_id"].dropna().unique())
        orphan_alias_refs = alias_ing_ids - ingredient_ids
        if orphan_alias_refs:
            errors.append(f"{len(orphan_alias_refs)} aliases reference non-existent canonical ingredients: {orphan_alias_refs}")

    is_valid = len(errors) == 0
    return ValidationResult(
        dataset_name=name,
        is_valid=is_valid,
        total_records=len(recipes_df) + len(nutrition_df) + len(ingredients_df) + len(links_df),
        valid_records=len(recipes_df) + len(nutrition_df) + len(ingredients_df) + len(links_df) if is_valid else 0,
        invalid_records=0 if is_valid else len(errors),
        errors=errors,
        warnings=warnings,
    )
