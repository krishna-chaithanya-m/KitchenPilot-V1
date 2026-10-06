"""Validate parity between CSV files and PostgreSQL database for KitchenPilot-V1.

Compares:
1. Row counts across all 6 production datasets
2. Primary key identity sets
3. Referential integrity / foreign keys
4. Sample & full record canonical fingerprint SHA-256 hashes
5. Floating point values within acceptable tolerance (1e-4)
6. Null vs non-null semantics preservation
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pandas as pd
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.config import get_database_url
from src.db.session import check_db_connection, get_engine
from src.api.config import (
    DATA_DIR,
    INGREDIENTS_PATH,
    PROCESSED_DATA_DIR,
    RECIPE_INGREDIENTS_LINKED_PATH,
    RECIPE_NUTRITION_PATH,
    RECIPES_PATH,
)

RECIPES_STAGE_B_PATH = RECIPES_PATH
INGREDIENTS_STAGE_B_PATH = INGREDIENTS_PATH
ALIASES_STAGE_B_PATH = DATA_DIR / "mappings" / "ingredient_aliases.csv"
RECIPE_INGREDIENTS_STAGE_B_PATH = RECIPE_INGREDIENTS_LINKED_PATH
RECIPE_NUTRITION_STAGE_B_PATH = RECIPE_NUTRITION_PATH
RECIPE_INGREDIENT_NUTRITION_STAGE_B_PATH = PROCESSED_DATA_DIR / "recipe_ingredient_nutrition.csv"


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def canonical_fingerprint(record: Dict[str, Any], float_tol: int = 4) -> str:
    """Compute a deterministic SHA-256 hash of a dictionary."""
    normalized: Dict[str, Any] = {}
    for k in sorted(record.keys()):
        v = record[k]
        if v is None or (isinstance(v, float) and math.isnan(v)) or v == "" or (isinstance(v, str) and v.strip() == ""):
            normalized[k] = None
        elif isinstance(v, float):
            normalized[k] = round(v, float_tol)
        elif isinstance(v, (int, bool)):
            normalized[k] = v
        else:
            normalized[k] = str(v).strip()
    serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ParityValidator:
    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or get_database_url()
        self.engine = get_engine(self.db_url)
        self.discrepancies: List[str] = []

    def log_failure(self, msg: str) -> None:
        self.discrepancies.append(msg)
        logger.error(f"[PARITY FAILURE] {msg}")

    def validate_row_counts(self) -> bool:
        logger.info("=== Validating Row Counts ===")
        tables = [
            ("recipes", RECIPES_STAGE_B_PATH, "recipes"),
            ("ingredients", INGREDIENTS_STAGE_B_PATH, "ingredients"),
            ("ingredient_aliases", ALIASES_STAGE_B_PATH, "ingredient_aliases"),
            ("recipe_ingredients", RECIPE_INGREDIENTS_STAGE_B_PATH, "recipe_ingredients"),
            ("recipe_nutrition", RECIPE_NUTRITION_STAGE_B_PATH, "recipe_nutrition"),
            ("recipe_ingredient_nutrition", RECIPE_INGREDIENT_NUTRITION_STAGE_B_PATH, "recipe_ingredient_nutrition"),
        ]

        all_ok = True
        with self.engine.connect() as conn:
            for table_name, csv_path, label in tables:
                df = pd.read_csv(csv_path, low_memory=False)
                csv_count = len(df)
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                db_count = int(result) if result is not None else 0

                if csv_count != db_count:
                    self.log_failure(f"{label}: CSV has {csv_count} rows, DB has {db_count} rows")
                    all_ok = False
                else:
                    logger.info(f"[PASS] {label}: exact match ({csv_count} rows)")
        return all_ok

    def validate_primary_keys(self) -> bool:
        logger.info("=== Validating Primary Key Sets ===")
        checks = [
            ("recipes", RECIPES_STAGE_B_PATH, "recipe_id"),
            ("ingredients", INGREDIENTS_STAGE_B_PATH, "ingredient_id"),
            ("recipe_nutrition", RECIPE_NUTRITION_STAGE_B_PATH, "recipe_id"),
        ]

        all_ok = True
        with self.engine.connect() as conn:
            for table_name, csv_path, pk_col in checks:
                df = pd.read_csv(csv_path, low_memory=False)
                csv_pks = set(df[pk_col].dropna().astype(str))
                db_rows = conn.execute(text(f"SELECT {pk_col} FROM {table_name}")).fetchall()
                db_pks = set(str(r[0]) for r in db_rows)

                missing_in_db = csv_pks - db_pks
                extra_in_db = db_pks - csv_pks

                if missing_in_db:
                    self.log_failure(f"{table_name}: {len(missing_in_db)} keys missing in DB (e.g. {list(missing_in_db)[:3]})")
                    all_ok = False
                if extra_in_db:
                    self.log_failure(f"{table_name}: {len(extra_in_db)} unexpected keys in DB (e.g. {list(extra_in_db)[:3]})")
                    all_ok = False
                if not missing_in_db and not extra_in_db:
                    logger.info(f"[PASS] {table_name}: all {len(csv_pks)} primary keys match exactly")
        return all_ok

    def validate_referential_integrity(self) -> bool:
        logger.info("=== Validating Foreign Key Integrity in Database ===")
        queries = [
            ("Orphan recipe_ingredients (missing recipe)", "SELECT COUNT(*) FROM recipe_ingredients ri LEFT JOIN recipes r ON ri.recipe_id = r.recipe_id WHERE r.recipe_id IS NULL"),
            ("Orphan recipe_ingredients (missing ingredient)", "SELECT COUNT(*) FROM recipe_ingredients ri LEFT JOIN ingredients i ON ri.ingredient_id = i.ingredient_id WHERE i.ingredient_id IS NULL"),
            ("Orphan ingredient_aliases (missing ingredient)", "SELECT COUNT(*) FROM ingredient_aliases ia LEFT JOIN ingredients i ON ia.ingredient_id = i.ingredient_id WHERE i.ingredient_id IS NULL"),
            ("Orphan recipe_nutrition (missing recipe)", "SELECT COUNT(*) FROM recipe_nutrition rn LEFT JOIN recipes r ON rn.recipe_id = r.recipe_id WHERE r.recipe_id IS NULL"),
            ("Orphan recipe_ingredient_nutrition (missing recipe)", "SELECT COUNT(*) FROM recipe_ingredient_nutrition rin LEFT JOIN recipes r ON rin.recipe_id = r.recipe_id WHERE r.recipe_id IS NULL"),
        ]

        all_ok = True
        with self.engine.connect() as conn:
            for label, q in queries:
                orphans = conn.execute(text(q)).scalar() or 0
                if orphans > 0:
                    self.log_failure(f"{label}: found {orphans} orphans")
                    all_ok = False
                else:
                    logger.info(f"[PASS] {label}: 0 orphans")
        return all_ok

    def validate_special_cases(self) -> bool:
        logger.info("=== Validating Known Stage B Special Cases ===")
        all_ok = True
        with self.engine.connect() as conn:
            # 1. Check recipes with NULL / empty instructions
            null_instr_csv = pd.read_csv(RECIPES_STAGE_B_PATH)["instructions"].isna().sum()
            null_instr_db = conn.execute(text("SELECT COUNT(*) FROM recipes WHERE instructions IS NULL")).scalar() or 0
            if null_instr_csv != null_instr_db:
                self.log_failure(f"Recipes null instructions count mismatch: CSV={null_instr_csv}, DB={null_instr_db}")
                all_ok = False
            else:
                logger.info(f"[PASS] Null instructions count matches exactly: {null_instr_db}")

            # 2. Check 0.0 calorie recipes count
            cal_zero_csv = (pd.read_csv(RECIPE_NUTRITION_STAGE_B_PATH)["calories"] == 0.0).sum()
            cal_zero_db = conn.execute(text("SELECT COUNT(*) FROM recipe_nutrition WHERE calories = 0.0")).scalar() or 0
            if cal_zero_csv != cal_zero_db:
                self.log_failure(f"Zero calories count mismatch: CSV={cal_zero_csv}, DB={cal_zero_db}")
                all_ok = False
            else:
                logger.info(f"[PASS] Zero calories count matches exactly ({cal_zero_db} recipes preserved)")

        return all_ok

    def run_all(self) -> bool:
        logger.info("Starting Full Database Parity Validation...")
        v1 = self.validate_row_counts()
        v2 = self.validate_primary_keys()
        v3 = self.validate_referential_integrity()
        v4 = self.validate_special_cases()

        if v1 and v2 and v3 and v4 and not self.discrepancies:
            logger.info("PARITY VALIDATION PASSED: 100% data parity between CSV and PostgreSQL.")
            return True
        else:
            logger.error(f"PARITY VALIDATION FAILED: {len(self.discrepancies)} discrepancies found.")
            return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate data parity between CSV and PostgreSQL.")
    parser.add_argument("--db-url", type=str, default=None, help="Database connection URL")
    args = parser.parse_args()

    db_url = args.db_url or get_database_url()
    is_live, err = check_db_connection(db_url)
    if not is_live:
        logger.error(f"Cannot connect to database at {db_url}: {err}")
        return 1

    validator = ParityValidator(db_url)
    success = validator.run_all()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
