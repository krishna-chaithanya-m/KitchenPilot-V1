"""Deterministic CSV to PostgreSQL Database Seeder for KitchenPilot.

Imports authoritative Stage B datasets into PostgreSQL with strict referential
integrity, validation, transaction rollback safety, and idempotency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from sqlalchemy import delete, select, text

ROOT_DIR = Path(__file__).resolve().parent.parent
os.chdir(ROOT_DIR)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.contracts import (
    validate_cross_dataset_integrity,
    validate_ingredient_aliases_dataset,
    validate_ingredient_dataset,
    validate_recipe_dataset,
    validate_recipe_ingredient_links,
    validate_recipe_ingredient_nutrition_dataset,
    validate_recipe_nutrition_dataset,
)
from src.db.models import (
    DatasetManifestMetadataModel,
    IngredientAliasModel,
    IngredientModel,
    RecipeIngredientModel,
    RecipeIngredientNutritionModel,
    RecipeModel,
    RecipeNutritionModel,
)
from src.db.session import check_db_connection, get_db_session, get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kitchenpilot.seeder")

BATCH_SIZE = 5000


def _safe_str(val: Any) -> Any:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    return s if s else None


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or pd.isna(val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None or pd.isna(val):
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_bool(val: Any, default: bool = False) -> bool:
    if val is None or pd.isna(val):
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes", "t")


def seed_database(mode: str = "replace") -> int:
    """Execute transactional database seeding from Stage B datasets."""
    logger.info("=" * 60)
    logger.info("KITCHENPILOT DATABASE SEEDER (Mode: %s)", mode.upper())
    logger.info("=" * 60)

    # 1. Verify database connectivity
    if not check_db_connection():
        logger.error(
            "Cannot connect to PostgreSQL database. Please ensure PostgreSQL is running "
            "and DATABASE_URL is configured correctly."
        )
        return 1

    # 2. File paths from Stage B contracts
    recipes_csv = Path("data/processed/recipes.csv")
    ingredients_csv = Path("data/processed/ingredients.csv")
    aliases_csv = Path("data/mappings/ingredients/ingredient_aliases.csv")
    links_csv = Path("data/processed/recipe_ingredients_linked.csv")
    nutrition_csv = Path("data/processed/recipe_nutrition.csv")
    ring_nutrition_csv = Path("data/processed/recipe_ingredient_nutrition.csv")
    manifest_json = Path("data/manifests/production_data_manifest.json")

    required_files = [
        recipes_csv, ingredients_csv, aliases_csv,
        links_csv, nutrition_csv, ring_nutrition_csv
    ]
    for p in required_files:
        if not p.is_file():
            logger.error("Required dataset artifact missing: %s", p)
            return 1

    # 3. Load datasets
    logger.info("Loading Stage B production datasets...")
    rec_df = pd.read_csv(recipes_csv, low_memory=False)
    ing_df = pd.read_csv(ingredients_csv, low_memory=False)
    alias_df = pd.read_csv(aliases_csv, low_memory=False)
    links_df = pd.read_csv(links_csv, low_memory=False)
    nut_df = pd.read_csv(nutrition_csv, low_memory=False)
    ring_nut_df = pd.read_csv(ring_nutrition_csv, low_memory=False)

    logger.info(
        "Read %d recipes, %d ingredients, %d aliases, %d links, %d recipe nutrition, %d ingredient nutrition.",
        len(rec_df), len(ing_df), len(alias_df), len(links_df), len(nut_df), len(ring_nut_df)
    )

    # 4. Pre-import contract validation
    logger.info("Validating dataset contracts before ingestion...")
    r_val = validate_recipe_dataset(rec_df)
    i_val = validate_ingredient_dataset(ing_df)
    a_val = validate_ingredient_aliases_dataset(alias_df)
    l_val = validate_recipe_ingredient_links(links_df)
    n_val = validate_recipe_nutrition_dataset(nut_df)
    rn_val = validate_recipe_ingredient_nutrition_dataset(ring_nut_df)
    c_val = validate_cross_dataset_integrity(rec_df, nut_df, ing_df, links_df, alias_df)

    for val in [r_val, i_val, a_val, l_val, n_val, rn_val, c_val]:
        if not val.is_valid:
            logger.error("Dataset validation failed: %s - %s", val.dataset_name, val.errors)
            return 1
    logger.info("All pre-import contract validations passed (0 errors).")

    # 5. Execute transactional seeding
    try:
        with get_db_session() as session:
            if mode == "replace":
                logger.info("Clearing existing catalog tables (reverse foreign-key order)...")
                session.execute(delete(DatasetManifestMetadataModel))
                session.execute(delete(RecipeIngredientNutritionModel))
                session.execute(delete(RecipeNutritionModel))
                session.execute(delete(RecipeIngredientModel))
                session.execute(delete(IngredientAliasModel))
                session.execute(delete(IngredientModel))
                session.execute(delete(RecipeModel))
                session.flush()

            # --- A. Seed Recipes ---
            recipe_records = []
            for _, r in rec_df.iterrows():
                recipe_records.append({
                    "recipe_id": str(r["recipe_id"]).strip(),
                    "recipe_name": str(r["recipe_name"]).strip(),
                    "name_local": _safe_str(r.get("name_local")),
                    "cuisine": _safe_str(r.get("cuisine")),
                    "region": _safe_str(r.get("region")),
                    "meal_type": _safe_str(r.get("meal_type")),
                    "category": _safe_str(r.get("category")),
                    "ingredients": _safe_str(r.get("ingredients")),
                    "instructions": _safe_str(r.get("instructions")),
                    "prep_time_min": _safe_int(r.get("prep_time_min")),
                    "cook_time_min": _safe_int(r.get("cook_time_min")),
                    "total_time_min": _safe_int(r.get("total_time_min")),
                    "servings": max(1, _safe_int(r.get("servings"), 1)),
                    "diet_type": _safe_str(r.get("diet_type")),
                    "vegetarian": _safe_bool(r.get("vegetarian")),
                    "vegan": _safe_bool(r.get("vegan")),
                    "jain": _safe_bool(r.get("jain")),
                    "satvik": _safe_bool(r.get("satvik")),
                    "contains": _safe_str(r.get("contains")),
                    "source_id": str(r.get("source_id", "M001")).strip(),
                    "source_license": str(r.get("source_license", "CC BY 4.0")).strip(),
                })
            if mode == "upsert":
                existing_recipe_ids = set(session.scalars(select(RecipeModel.recipe_id)).all())
                to_insert_rec = [r for r in recipe_records if r["recipe_id"] not in existing_recipe_ids]
                to_update_rec = [r for r in recipe_records if r["recipe_id"] in existing_recipe_ids]
                if to_insert_rec:
                    logger.info("Inserting %d new recipes...", len(to_insert_rec))
                    session.bulk_insert_mappings(RecipeModel, to_insert_rec)
                if to_update_rec:
                    logger.info("Updating %d existing recipes...", len(to_update_rec))
                    session.bulk_update_mappings(RecipeModel, to_update_rec)
            else:
                logger.info("Ingesting recipes (%d records)...", len(rec_df))
                session.bulk_insert_mappings(RecipeModel, recipe_records)
            session.flush()

            # --- B. Seed Canonical Ingredients ---
            from src.ingredients.ontology import IngredientOntology
            ont = IngredientOntology.load()
            ing_map = {i.ingredient_id: i for i in ont.all_ingredients()}

            ingredient_records = []
            for _, r in ing_df.iterrows():
                cid = str(r["ingredient_id"]).strip()
                domain_ing = ing_map.get(cid)
                ingredient_records.append({
                    "ingredient_id": cid,
                    "canonical_name": str(r["canonical_name"]).strip(),
                    "display_name": str(r["display_name"]).strip(),
                    "ingredient_form": str(r.get("ingredient_form", "default")).strip(),
                    "category": str(r.get("category", "other")).strip(),
                    "recipe_occurrence_count": _safe_int(r.get("recipe_occurrence_count")),
                    "candidate_variant_count": _safe_int(r.get("candidate_variant_count")),
                    "source": str(r.get("source", "Indian recipe corpus")).strip(),
                    "mapping_status": str(r.get("mapping_status", "VALIDATED_AUTO")).strip(),
                    "vegetarian": domain_ing.vegetarian if domain_ing else True,
                    "vegan": domain_ing.vegan if domain_ing else True,
                    "allergen_flags": domain_ing.allergen_flags if domain_ing else [],
                    "nutrition_reference": domain_ing.nutrition_reference if domain_ing else None,
                    "default_unit": domain_ing.default_unit if domain_ing else "g",
                    "active": True,
                })
            if mode == "upsert":
                existing_ing_ids = set(session.scalars(select(IngredientModel.ingredient_id)).all())
                to_insert_ing = [r for r in ingredient_records if r["ingredient_id"] not in existing_ing_ids]
                to_update_ing = [r for r in ingredient_records if r["ingredient_id"] in existing_ing_ids]
                if to_insert_ing:
                    logger.info("Inserting %d new canonical ingredients...", len(to_insert_ing))
                    session.bulk_insert_mappings(IngredientModel, to_insert_ing)
                if to_update_ing:
                    logger.info("Updating %d existing canonical ingredients...", len(to_update_ing))
                    session.bulk_update_mappings(IngredientModel, to_update_ing)
            else:
                logger.info("Ingesting canonical ingredients (%d records)...", len(ing_df))
                session.bulk_insert_mappings(IngredientModel, ingredient_records)
            session.flush()

            # --- C. Seed Ingredient Aliases ---
            alias_records = []
            for _, r in alias_df.iterrows():
                alias_records.append({
                    "alias_id": str(r["alias_id"]).strip(),
                    "canonical_ingredient_id": str(r["canonical_ingredient_id"]).strip(),
                    "alias": str(r["alias"]).strip(),
                    "normalized_alias": str(r["normalized_alias"]).strip(),
                    "source": str(r.get("source", "corpus")).strip(),
                    "confidence": _safe_float(r.get("confidence", 1.0)),
                    "review_status": str(r.get("review_status", "VALIDATED")).strip(),
                })
            if mode == "upsert":
                existing_alias_ids = set(session.scalars(select(IngredientAliasModel.alias_id)).all())
                to_insert_alias = [r for r in alias_records if r["alias_id"] not in existing_alias_ids]
                to_update_alias = [r for r in alias_records if r["alias_id"] in existing_alias_ids]
                if to_insert_alias:
                    logger.info("Inserting %d new ingredient aliases...", len(to_insert_alias))
                    session.bulk_insert_mappings(IngredientAliasModel, to_insert_alias)
                if to_update_alias:
                    logger.info("Updating %d existing ingredient aliases...", len(to_update_alias))
                    session.bulk_update_mappings(IngredientAliasModel, to_update_alias)
            else:
                logger.info("Ingesting ingredient aliases (%d records)...", len(alias_df))
                session.bulk_insert_mappings(IngredientAliasModel, alias_records)
            session.flush()

            # --- D. Seed Recipe-Ingredient Links (Batched) ---
            existing_links = session.execute(text("SELECT COUNT(*) FROM recipe_ingredients")).scalar() or 0
            if mode == "upsert" and existing_links > 0:
                logger.info("Preserving %d existing recipe-ingredient links in database.", existing_links)
            else:
                logger.info("Ingesting recipe-ingredient links (%d records in batches of %d)...", len(links_df), BATCH_SIZE)
                valid_ing_ids = set(ing_df["ingredient_id"].str.strip())
                link_records = []
                for idx, r in links_df.iterrows():
                    cid = _safe_str(r.get("ingredient_id"))
                    if cid and cid not in valid_ing_ids:
                        cid = None

                    link_records.append({
                        "recipe_id": str(r["recipe_id"]).strip(),
                        "original_ingredient": str(r["original_ingredient"]),
                        "quantity": _safe_str(r.get("quantity")),
                        "unit": _safe_str(r.get("unit")),
                        "ingredient": _safe_str(r.get("ingredient")),
                        "preparation": _safe_str(r.get("preparation")),
                        "ingredient_id": cid,
                        "canonical_ingredient": _safe_str(r.get("canonical_ingredient")),
                        "display_name": _safe_str(r.get("display_name")),
                        "ingredient_form": _safe_str(r.get("ingredient_form")),
                        "category": _safe_str(r.get("category")),
                        "mapping_status": str(r.get("mapping_status", "REVIEW")).strip(),
                        "mapping_source": str(r.get("mapping_source", "NONE")).strip(),
                    })
                    if len(link_records) >= BATCH_SIZE:
                        session.bulk_insert_mappings(RecipeIngredientModel, link_records)
                        session.flush()
                        link_records.clear()

                if link_records:
                    session.bulk_insert_mappings(RecipeIngredientModel, link_records)
                    session.flush()
                    link_records.clear()

            # --- E. Seed Recipe Nutrition ---
            nutrition_records = []
            for _, r in nut_df.iterrows():
                nutrition_records.append({
                    "recipe_id": str(r["recipe_id"]).strip(),
                    "recipe_name": str(r["recipe_name"]).strip(),
                    "servings": max(1, _safe_int(r.get("servings"), 1)),
                    "total_calories_kcal": _safe_float(r.get("total_calories_kcal")),
                    "total_protein_g": _safe_float(r.get("total_protein_g")),
                    "total_fat_g": _safe_float(r.get("total_fat_g")),
                    "total_carbs_g": _safe_float(r.get("total_carbs_g")),
                    "total_fiber_g": _safe_float(r.get("total_fiber_g")),
                    "total_sugar_g": _safe_float(r.get("total_sugar_g")),
                    "total_sodium_mg": _safe_float(r.get("total_sodium_mg")),
                    "per_serving_calories_kcal": _safe_float(r.get("per_serving_calories_kcal")),
                    "per_serving_protein_g": _safe_float(r.get("per_serving_protein_g")),
                    "per_serving_fat_g": _safe_float(r.get("per_serving_fat_g")),
                    "per_serving_carbs_g": _safe_float(r.get("per_serving_carbs_g")),
                    "per_serving_fiber_g": _safe_float(r.get("per_serving_fiber_g")),
                    "per_serving_sugar_g": _safe_float(r.get("per_serving_sugar_g")),
                    "per_serving_sodium_mg": _safe_float(r.get("per_serving_sodium_mg")),
                    "nutrition_quality": str(r.get("nutrition_quality", "PARTIAL")).strip(),
                    "ingredient_count": _safe_int(r.get("ingredient_count")),
                    "calculated_ingredient_count": _safe_int(r.get("calculated_ingredient_count")),
                    "unmapped_ingredient_count": _safe_int(r.get("unmapped_ingredient_count")),
                    "no_match_ingredient_count": _safe_int(r.get("no_match_ingredient_count")),
                    "needs_review_ingredient_count": _safe_int(r.get("needs_review_ingredient_count")),
                    "qualitative_quantity_count": _safe_int(r.get("qualitative_quantity_count")),
                    "conversion_failure_count": _safe_int(r.get("conversion_failure_count")),
                    "state_mismatch_count": _safe_int(r.get("state_mismatch_count")),
                })
            if mode == "upsert":
                existing_nut_ids = set(session.scalars(select(RecipeNutritionModel.recipe_id)).all())
                to_insert_nut = [r for r in nutrition_records if r["recipe_id"] not in existing_nut_ids]
                to_update_nut = [r for r in nutrition_records if r["recipe_id"] in existing_nut_ids]
                if to_insert_nut:
                    logger.info("Inserting %d new recipe nutrition records...", len(to_insert_nut))
                    session.bulk_insert_mappings(RecipeNutritionModel, to_insert_nut)
                if to_update_nut:
                    logger.info("Updating %d existing recipe nutrition records...", len(to_update_nut))
                    session.bulk_update_mappings(RecipeNutritionModel, to_update_nut)
            else:
                logger.info("Ingesting recipe nutrition (%d records)...", len(nut_df))
                session.bulk_insert_mappings(RecipeNutritionModel, nutrition_records)
            session.flush()

            # --- F. Seed Recipe Ingredient Nutrition (Batched) ---
            existing_ring = session.execute(text("SELECT COUNT(*) FROM recipe_ingredient_nutrition")).scalar() or 0
            if mode == "upsert" and existing_ring > 0:
                logger.info("Preserving %d existing recipe ingredient nutrition records in database.", existing_ring)
            else:
                logger.info("Ingesting recipe ingredient nutrition (%d records in batches of %d)...", len(ring_nut_df), BATCH_SIZE)
                ring_nut_records = []
                for _, r in ring_nut_df.iterrows():
                    ring_nut_records.append({
                        "recipe_id": str(r["recipe_id"]).strip(),
                        "original_ingredient": str(r["original_ingredient"]),
                        "ingredient": str(r["ingredient"]).strip(),
                        "quantity": _safe_str(r.get("quantity")),
                        "unit": _safe_str(r.get("unit")),
                        "preparation": _safe_str(r.get("preparation")),
                        "ingredient_id": _safe_str(r.get("ingredient_id")),
                        "canonical_ingredient": _safe_str(r.get("canonical_ingredient")),
                        "mapping_status": str(r.get("mapping_status", "UNMAPPED")).strip(),
                        "curation_status": _safe_str(r.get("curation_status")),
                        "cnf_food_code": _safe_float(r.get("cnf_food_code"), default=None),
                        "cnf_food_name": _safe_str(r.get("cnf_food_name")),
                        "parsed_quantity": _safe_float(r.get("parsed_quantity"), default=None),
                        "quantity_parse_status": str(r.get("quantity_parse_status", "PARSED_NUMERIC")).strip(),
                        "normalized_unit": _safe_str(r.get("normalized_unit")),
                        "grams": _safe_float(r.get("grams"), default=None),
                        "conversion_status": str(r.get("conversion_status", "UNMAPPED")).strip(),
                        "state_status": str(r.get("state_status", "MATCHED")).strip(),
                        "energy_kcal": _safe_float(r.get("energy_kcal")),
                        "protein_g": _safe_float(r.get("protein_g")),
                        "fat_g": _safe_float(r.get("fat_g")),
                        "carbs_g": _safe_float(r.get("carbs_g")),
                        "fiber_g": _safe_float(r.get("fiber_g")),
                        "sugar_g": _safe_float(r.get("sugar_g")),
                        "sodium_mg": _safe_float(r.get("sodium_mg")),
                        "mapping_quality": str(r.get("mapping_quality", "UNAVAILABLE")).strip(),
                        "nutrition_quality": str(r.get("nutrition_quality", "UNAVAILABLE")).strip(),
                        "nutrition_source": str(r.get("nutrition_source", "NONE")).strip(),
                        "calculation_notes": _safe_str(r.get("calculation_notes")),
                    })
                    if len(ring_nut_records) >= BATCH_SIZE:
                        session.bulk_insert_mappings(RecipeIngredientNutritionModel, ring_nut_records)
                        session.flush()
                        ring_nut_records.clear()

                if ring_nut_records:
                    session.bulk_insert_mappings(RecipeIngredientNutritionModel, ring_nut_records)
                    session.flush()
                    ring_nut_records.clear()

            # --- G. Seed Manifest Audit Metadata ---
            logger.info("Recording dataset manifest provenance metadata...")
            def _sha256(fp: Path) -> str:
                h = hashlib.sha256()
                with open(fp, "rb") as f:
                    while chunk := f.read(65536):
                        h.update(chunk)
                return h.hexdigest()

            now = datetime.now(timezone.utc)
            metadata_items = [
                DatasetManifestMetadataModel(
                    dataset_name="recipes",
                    dataset_version="0.1.0",
                    source="Indian Food 6000+ Recipes Dataset (Kaggle)",
                    imported_at=now,
                    row_count=len(rec_df),
                    checksum_sha256=_sha256(recipes_csv),
                    schema_version="0.1.0",
                    import_status="SUCCESS",
                ),
                DatasetManifestMetadataModel(
                    dataset_name="ingredients",
                    dataset_version="0.1.0",
                    source="Indian Recipe Corpus + Multi-stage Normalization",
                    imported_at=now,
                    row_count=len(ing_df),
                    checksum_sha256=_sha256(ingredients_csv),
                    schema_version="0.1.0",
                    import_status="SUCCESS",
                ),
                DatasetManifestMetadataModel(
                    dataset_name="ingredient_aliases",
                    dataset_version="0.1.0",
                    source="Stage B Verified & Derived Aliases",
                    imported_at=now,
                    row_count=len(alias_df),
                    checksum_sha256=_sha256(aliases_csv),
                    schema_version="0.1.0",
                    import_status="SUCCESS",
                ),
                DatasetManifestMetadataModel(
                    dataset_name="recipe_ingredients_linked",
                    dataset_version="0.1.0",
                    source="Stage B Relational Recipe Ingredient Linkage",
                    imported_at=now,
                    row_count=len(links_df),
                    checksum_sha256=_sha256(links_csv),
                    schema_version="0.1.0",
                    import_status="SUCCESS",
                ),
                DatasetManifestMetadataModel(
                    dataset_name="recipe_nutrition",
                    dataset_version="0.1.0",
                    source="Health Canada CNF 2026 + Indian Culinary Calibrations",
                    imported_at=now,
                    row_count=len(nut_df),
                    checksum_sha256=_sha256(nutrition_csv),
                    schema_version="0.1.0",
                    import_status="SUCCESS",
                ),
                DatasetManifestMetadataModel(
                    dataset_name="recipe_ingredient_nutrition",
                    dataset_version="0.1.0",
                    source="Health Canada CNF 2026 Per-Item Breakdown",
                    imported_at=now,
                    row_count=len(ring_nut_df),
                    checksum_sha256=_sha256(ring_nutrition_csv),
                    schema_version="0.1.0",
                    import_status="SUCCESS",
                ),
            ]
            if mode == "upsert":
                session.execute(delete(DatasetManifestMetadataModel))
            session.add_all(metadata_items)
            session.flush()

        logger.info("Transaction committed successfully.")
    except Exception as exc:
        logger.exception("Database seeding failed; transaction rolled back: %s", exc)
        return 1

    logger.info("=" * 60)
    logger.info("ALL DATASETS SEEDED SUCCESSFULLY INTO POSTGRESQL")
    logger.info("=" * 60)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed KitchenPilot PostgreSQL database from Stage B datasets.")
    parser.add_argument(
        "--mode",
        choices=["replace", "upsert"],
        default="replace",
        help="Seeding mode: 'replace' drops existing records before reload, 'upsert' preserves existing.",
    )
    args = parser.parse_args()
    return seed_database(mode=args.mode)


if __name__ == "__main__":
    sys.exit(main())
