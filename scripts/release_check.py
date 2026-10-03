"""KitchenPilot-V1 — Automated Release Verification Script.

Performs lightweight automated checks before release:
- Required directory structure exists
- Required frontend assets exist
- Required model artifacts exist
- Required processed datasets exist
- requirements.txt exists
- README.md exists
- .env.example exists
- VERSION exists and contains valid semantic version (1.0.0)
- Critical project modules import cleanly
- Recommendation artifacts are readable
- No secret files (such as .env) are present in the release tree

Exit code:
0 = PASS
1 = FAIL
"""

import os
import re
import sys
from pathlib import Path


def main() -> int:
    root_dir = Path(__file__).resolve().parent.parent
    os.chdir(root_dir)
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    print("=" * 60)
    print("KitchenPilot-V1 Release Verification")
    print(f"Project root: {root_dir}")
    print("=" * 60)

    failures = []

    # 1. Version file check
    version_file = root_dir / "VERSION"
    if not version_file.is_file():
        failures.append("VERSION file missing at project root.")
    else:
        version_text = version_file.read_text(encoding="utf-8").strip()
        semver_pattern = re.compile(r"^\d+\.\d+\.\d+$")
        if not semver_pattern.match(version_text):
            failures.append(f"VERSION is '{version_text}', expected valid semantic version (MAJOR.MINOR.PATCH).")
        else:
            print(f" [PASS] VERSION: {version_text}")

    # 2. Key configuration / documentation files
    key_files = ["requirements.txt", "README.md", ".env.example", ".gitignore"]
    for kf in key_files:
        path = root_dir / kf
        if not path.is_file():
            failures.append(f"Essential file missing: {kf}")
        else:
            print(f" [PASS] File exists: {kf}")

    # 3. Required directories
    required_dirs = [
        "data/processed",
        "models/recommendation",
        "src/api",
        "src/recommendation",
        "src/nutrition",
        "frontend/css",
        "frontend/js",
        "scripts",
        "tests",
    ]
    for rd in required_dirs:
        path = root_dir / rd
        if not path.is_dir():
            failures.append(f"Required directory missing: {rd}")
        else:
            print(f" [PASS] Directory exists: {rd}")

    # 4. Required frontend files
    required_frontend_files = [
        "frontend/index.html",
        "frontend/recipes.html",
        "frontend/recipe.html",
        "frontend/recommendations.html",
        "frontend/css/style.css",
        "frontend/js/api.js",
    ]
    for ff in required_frontend_files:
        path = root_dir / ff
        if not path.is_file():
            failures.append(f"Frontend asset missing: {ff}")
        else:
            print(f" [PASS] Frontend asset exists: {ff}")

    # 5. Required model artifacts
    required_models = [
        "models/recommendation/tfidf_vectorizer.joblib",
        "models/recommendation/recipe_tfidf_matrix.npz",
        "models/recommendation/recipe_index.csv",
    ]
    for rm in required_models:
        path = root_dir / rm
        if not path.is_file():
            failures.append(f"Model artifact missing: {rm}")
        else:
            print(f" [PASS] Model artifact exists: {rm}")

    # 6. Required processed datasets
    required_datasets = [
        "data/processed/recipes.csv",
        "data/processed/recipe_nutrition.csv",
        "data/processed/recipe_corpus.csv",
        "data/processed/recipe_ingredients_linked.csv",
        "data/processed/ingredients.csv",
    ]
    for rds in required_datasets:
        path = root_dir / rds
        if not path.is_file():
            failures.append(f"Processed dataset missing: {rds}")
        else:
            print(f" [PASS] Dataset exists: {rds}")

    # 7. No secret files in release tree
    secret_files = [".env", ".env.local", ".env.production"]
    for sf in secret_files:
        path = root_dir / sf
        if path.exists():
            failures.append(f"Forbidden secret file found in project tree: {sf}")
        else:
            print(f" [PASS] Secret file not present: {sf}")

    # 8. Critical module imports
    print(" Verifying critical module imports...")
    try:
        import src.api.main
        import src.recommendation.recommender
        import src.nutrition.recipe_nutrition_engine
        print(" [PASS] Critical modules imported successfully.")
    except Exception as exc:
        failures.append(f"Import failure: {exc}")

    # 9. Verify model readability
    print(" Verifying model readability...")
    try:
        import joblib
        import scipy.sparse as sp
        import pandas as pd

        vec = joblib.load(root_dir / "models/recommendation/tfidf_vectorizer.joblib")
        mat = sp.load_npz(root_dir / "models/recommendation/recipe_tfidf_matrix.npz")
        idx = pd.read_csv(root_dir / "models/recommendation/recipe_index.csv")

        if mat.shape[0] != len(idx):
            failures.append(f"Matrix rows ({mat.shape[0]}) mismatch recipe index count ({len(idx)}).")
        else:
            print(f" [PASS] Model artifacts loaded cleanly ({len(idx)} recipes indexed, vocab size: {len(vec.vocabulary_)}).")
    except Exception as exc:
        failures.append(f"Model artifact verification error: {exc}")

    print("=" * 60)
    if failures:
        print(f"RELEASE CHECK FAILED with {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ALL RELEASE CHECKS PASSED.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
