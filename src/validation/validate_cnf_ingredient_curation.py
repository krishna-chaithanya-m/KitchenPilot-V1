"""Validate the programmatically curated KitchenPilot-to-CNF ingredient mapping."""

import hashlib
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pandas as pd
except ImportError:
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file() and Path(sys.executable) != venv_python:
        result = subprocess.run([str(venv_python)] + sys.argv, cwd=str(PROJECT_ROOT))
        sys.exit(result.returncode)
    raise

INGREDIENTS_FILE = PROJECT_ROOT / "data/processed/ingredients.csv"
CNF_FILE = PROJECT_ROOT / "data/processed/cnf_2026_nutrition.csv"
REVIEW_FILE = PROJECT_ROOT / "data/mappings/cnf_ingredient_mapping_review.csv"
VALIDATED_MAPPING_FILE = PROJECT_ROOT / "data/mappings/final_ingredient_mapping_validated.csv"
LINKED_RECIPES_FILE = PROJECT_ROOT / "data/processed/recipe_ingredients_linked.csv"

CURATED_OUTPUT_FILE = PROJECT_ROOT / "data/mappings/cnf_ingredient_mapping_curated.csv"
REPORT_OUTPUT_FILE = PROJECT_ROOT / "data/mappings/cnf_ingredient_curation_report.csv"

REQUIRED_CURATED_COLUMNS = [
    "ingredient_id",
    "canonical_name",
    "display_name",
    "ingredient_form",
    "category",
    "cnf_food_code",
    "cnf_food_name",
    "cnf_food_form",
    "cnf_food_description",
    "match_method",
    "match_score",
    "curation_status",
    "curation_reason",
    "curation_source",
    "recipe_form_evidence",
    "review_notes",
]

REQUIRED_REPORT_COLUMNS = [
    "ingredient_id",
    "canonical_name",
    "ingredient_form",
    "top_candidate",
    "selected_candidate",
    "curation_status",
    "curation_reason",
    "candidate_count",
]

ALLOWED_STATUSES = {"APPROVED", "NO_MATCH", "NEEDS_REVIEW"}

BASELINE_HASHES = {
    INGREDIENTS_FILE: "8d9d81a8ea9570709e4bde040d4d52bc1f3fcc4087e7dff6d60f76555f962fe8",
    CNF_FILE: "50fa55fd30801aa42cb06102fecf9ac6969f0486bf95fee5dbae698ed8b1a70b",
    REVIEW_FILE: "21b24b2bd0a2656d4971f994980986b4301ac5a1f7fb14a15e212b9fc28045c5",
    VALIDATED_MAPPING_FILE: "a7222b91124d2d776dca96e78111b5a328a45f2d430d500364deba6d86c87e36",
    LINKED_RECIPES_FILE: "edc9ced314a1724330cef4c896b314d9f9614640ca5de39780192c69a89efb6c",
}


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


def validate() -> dict[str, int]:
    """Run all validation checks and return summary statistics."""
    # 9. Verify protected source files are unchanged
    for file_path, expected_hash in BASELINE_HASHES.items():
        if not file_path.is_file():
            raise FileNotFoundError(f"Protected source file not found: {file_path}")
        actual_hash = _sha256(file_path)
        if actual_hash != expected_hash:
            raise ValueError(f"Protected input file has changed: {file_path}")

    # Read tables
    curated = _read_csv(CURATED_OUTPUT_FILE)
    report = _read_csv(REPORT_OUTPUT_FILE)
    ingredients = _read_csv(INGREDIENTS_FILE)
    cnf = _read_csv(CNF_FILE).drop_duplicates("source_food_id")

    # Column existence
    for col in REQUIRED_CURATED_COLUMNS:
        if col not in curated.columns:
            raise ValueError(f"Missing required column in curated file: {col}")
    for col in REQUIRED_REPORT_COLUMNS:
        if col not in report.columns:
            raise ValueError(f"Missing required column in report file: {col}")

    # 1. Coverage: Exactly 128 canonical ingredient IDs are represented
    if len(curated) != 128:
        raise ValueError(f"Expected 128 curated rows, got {len(curated)}")
    if len(report) != 128:
        raise ValueError(f"Expected 128 report rows, got {len(report)}")

    # 2. No duplicate ingredient_id
    if curated["ingredient_id"].duplicated().any():
        dups = curated[curated["ingredient_id"].duplicated()]["ingredient_id"].tolist()
        raise ValueError(f"Duplicate ingredient_id found in curated file: {dups}")
    if report["ingredient_id"].duplicated().any():
        dups = report[report["ingredient_id"].duplicated()]["ingredient_id"].tolist()
        raise ValueError(f"Duplicate ingredient_id found in report file: {dups}")

    # 3. Every ingredient_id exists in ingredients.csv
    expected_ids = set(ingredients["ingredient_id"])
    actual_curated_ids = set(curated["ingredient_id"])
    actual_report_ids = set(report["ingredient_id"])
    if actual_curated_ids != expected_ids:
        missing = expected_ids - actual_curated_ids
        extra = actual_curated_ids - expected_ids
        raise ValueError(f"Ingredient ID mismatch in curated table: missing={missing}, extra={extra}")
    if actual_report_ids != expected_ids:
        missing = expected_ids - actual_report_ids
        extra = actual_report_ids - expected_ids
        raise ValueError(f"Ingredient ID mismatch in report table: missing={missing}, extra={extra}")

    # 8. Status values: Valid curation_status values only
    curated_statuses = set(curated["curation_status"])
    if not curated_statuses.issubset(ALLOWED_STATUSES):
        invalid = curated_statuses - ALLOWED_STATUSES
        raise ValueError(f"Invalid curation_status found: {invalid}")

    # 4. CNF IDs: Every APPROVED CNF food code exists in CNF 2026
    cnf_food_ids = set(cnf["source_food_id"])
    approved = curated[curated["curation_status"] == "APPROVED"]
    approved_codes = set(approved["cnf_food_code"])
    unknown_codes = approved_codes - cnf_food_ids
    if unknown_codes:
        raise ValueError(f"APPROVED rows reference nonexistent CNF food code(s): {unknown_codes}")

    # 5. NO_MATCH integrity: NO_MATCH records have blank CNF mapping fields
    no_match = curated[curated["curation_status"] == "NO_MATCH"]
    if no_match["cnf_food_code"].ne("").any():
        raise ValueError("NO_MATCH rows must have blank cnf_food_code")
    if no_match["cnf_food_name"].ne("").any():
        raise ValueError("NO_MATCH rows must have blank cnf_food_name")
    if no_match["cnf_food_form"].ne("").any():
        raise ValueError("NO_MATCH rows must have blank cnf_food_form")
    if no_match["cnf_food_description"].ne("").any():
        raise ValueError("NO_MATCH rows must have blank cnf_food_description")

    # 6. APPROVED mapping integrity: APPROVED records have a CNF food code and name
    if approved["cnf_food_code"].eq("").any():
        raise ValueError("APPROVED rows must have non-blank cnf_food_code")
    if approved["cnf_food_name"].eq("").any():
        raise ValueError("APPROVED rows must have non-blank cnf_food_name")

    # 7. NEEDS_REVIEW records are clearly identified
    needs_review = curated[curated["curation_status"] == "NEEDS_REVIEW"]
    for _, nr_row in needs_review.iterrows():
        nr_code = nr_row["cnf_food_code"]
        if nr_code and nr_code not in cnf_food_ids:
            raise ValueError(f"NEEDS_REVIEW row references invalid CNF food code: {nr_code}")

    # 10. No duplicate canonical ingredients
    if curated.duplicated(["canonical_name", "ingredient_form"]).any():
        dups = curated[curated.duplicated(["canonical_name", "ingredient_form"])][
            ["canonical_name", "ingredient_form"]
        ]
        raise ValueError(f"Duplicate canonical_name and form found: {dups.to_dict('records')}")

    # 11. Form information is preserved
    ing_by_id = ingredients.set_index("ingredient_id")
    for _, row in curated.iterrows():
        iid = row["ingredient_id"]
        expected_form = ing_by_id.loc[iid, "ingredient_form"]
        if row["ingredient_form"] != expected_form:
            raise ValueError(
                f"Form mismatch for {iid}: expected {expected_form}, got {row['ingredient_form']}"
            )

    # 12. Curation reasons are not blank
    if curated["curation_reason"].str.strip().eq("").any():
        empty_reasons = curated[curated["curation_reason"].str.strip().eq("")]["ingredient_id"].tolist()
        raise ValueError(f"Curation reason is blank for ingredients: {empty_reasons}")

    return {
        "canonical_ingredients": len(curated),
        "approved": len(approved),
        "no_match": len(no_match),
        "needs_review": len(needs_review),
        "unique_approved_cnf_foods": approved["cnf_food_code"].nunique(),
    }


def main() -> None:
    stats = validate()
    print("==================================================")
    print("CNF INGREDIENT CURATION VALIDATION")
    print("==================================================")
    print("\nCoverage: PASS")
    print("Duplicate ingredients: PASS")
    print("CNF IDs: PASS")
    print("Status values: PASS")
    print("NO_MATCH integrity: PASS")
    print("APPROVED mapping integrity: PASS")
    print("Form preservation: PASS")
    print("Curation reasons: PASS")
    print("Existing inputs unchanged: PASS")
    print("\nValidation result: PASS")


if __name__ == "__main__":
    main()
