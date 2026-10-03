"""KitchenPilot-V1 — Release & Package Integrity Tests.

Verifies that the release artifacts, version metadata, configuration templates,
and essential directories conform to the 1.0.0 release specification without
duplicating existing nutrition or recommendation test suites.
"""

from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_version_metadata():
    """Verify VERSION file exists, is readable, and contains a valid semantic version."""
    version_file = ROOT_DIR / "VERSION"
    assert version_file.is_file(), "VERSION file missing from project root"
    content = version_file.read_text(encoding="utf-8").strip()
    import re
    assert re.match(r"^\d+\.\d+\.\d+$", content), f"Expected valid semantic version, found '{content}'"


def test_release_manifest_exists():
    """Verify RELEASE_MANIFEST.md exists and contains release declarations."""
    manifest_file = ROOT_DIR / "RELEASE_MANIFEST.md"
    assert manifest_file.is_file(), "RELEASE_MANIFEST.md missing from project root"
    content = manifest_file.read_text(encoding="utf-8")
    assert "KitchenPilot-V1" in content
    assert "1.0.0" in content
    assert "CNF 2026" in content


def test_environment_template_and_no_secrets():
    """Verify .env.example exists and live .env secret files are not present."""
    env_example = ROOT_DIR / ".env.example"
    assert env_example.is_file(), ".env.example must exist in project root"

    env_live = ROOT_DIR / ".env"
    assert not env_live.exists(), "Live .env file must not be committed or present in clean release tree"


def test_required_directory_structure():
    """Verify all top-level architectural modules and directories exist."""
    required_dirs = [
        "src/api",
        "src/nutrition",
        "src/recommendation",
        "src/ingestion",
        "src/cleaning",
        "src/validation",
        "src/evaluation",
        "data/processed",
        "models/recommendation",
        "frontend/css",
        "frontend/js",
        "scripts",
        "tests",
    ]
    for rel_dir in required_dirs:
        d = ROOT_DIR / rel_dir
        assert d.is_dir(), f"Expected directory '{rel_dir}' to exist"


def test_required_frontend_assets():
    """Verify all HTML, CSS, and JS assets exist for the static frontend."""
    required_assets = [
        "frontend/index.html",
        "frontend/recipes.html",
        "frontend/recipe.html",
        "frontend/recommendations.html",
        "frontend/css/style.css",
        "frontend/js/api.js",
    ]
    for asset in required_assets:
        p = ROOT_DIR / asset
        assert p.is_file(), f"Frontend asset '{asset}' missing"


def test_required_model_artifacts():
    """Verify frozen TF-IDF model artifacts exist."""
    model_files = [
        "models/recommendation/tfidf_vectorizer.joblib",
        "models/recommendation/recipe_tfidf_matrix.npz",
        "models/recommendation/recipe_index.csv",
    ]
    for mf in model_files:
        p = ROOT_DIR / mf
        assert p.is_file(), f"Model artifact '{mf}' missing"
        assert p.stat().st_size > 0, f"Model artifact '{mf}' is empty"


def test_required_processed_datasets():
    """Verify frozen recipe and nutrition datasets exist."""
    dataset_files = [
        "data/processed/recipes.csv",
        "data/processed/recipe_nutrition.csv",
        "data/processed/recipe_corpus.csv",
        "data/processed/recipe_ingredients_linked.csv",
        "data/processed/ingredients.csv",
    ]
    for df in dataset_files:
        p = ROOT_DIR / df
        assert p.is_file(), f"Dataset file '{df}' missing"
        assert p.stat().st_size > 0, f"Dataset file '{df}' is empty"


def test_critical_module_imports():
    """Verify critical entrypoint modules can be imported cleanly."""
    import src.api.main
    import src.nutrition.recipe_nutrition_engine
    import src.recommendation.recommender

    assert hasattr(src.api.main, "app"), "FastAPI 'app' missing in src.api.main"
    assert hasattr(src.recommendation.recommender, "KitchenPilotRecommender")
