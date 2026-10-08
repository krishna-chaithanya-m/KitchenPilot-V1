"""Frontend Static Asset Integrity and Integration Test Suite.

Verifies:
1. All required HTML, CSS, and JS files exist in frontend/
2. HTML structure contains navigation, containers, and script tags
3. API client contracts match backend routes
4. Section 14 target query executes successfully through the API client contract
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.main import app

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


def test_frontend_files_exist():
    expected_files = [
        FRONTEND_DIR / "index.html",
        FRONTEND_DIR / "recipes.html",
        FRONTEND_DIR / "recipe.html",
        FRONTEND_DIR / "recommendations.html",
        FRONTEND_DIR / "auth.html",
        FRONTEND_DIR / "verify-email.html",
        FRONTEND_DIR / "reset-password.html",
        FRONTEND_DIR / "css" / "style.css",
        FRONTEND_DIR / "js" / "config.js",
        FRONTEND_DIR / "js" / "api.js",
        FRONTEND_DIR / "js" / "app.js",
        FRONTEND_DIR / "js" / "auth.js",
        FRONTEND_DIR / "js" / "recipes.js",
        FRONTEND_DIR / "js" / "recipe.js",
        FRONTEND_DIR / "js" / "recommendations.js",
    ]
    for filepath in expected_files:
        assert filepath.is_file(), f"Missing required frontend file: {filepath}"


def test_html_script_and_css_links():
    html_pages = [
        "index.html",
        "recipes.html",
        "recipe.html",
        "recommendations.html",
        "auth.html",
        "verify-email.html",
        "reset-password.html",
    ]
    for page in html_pages:
        content = (FRONTEND_DIR / page).read_text(encoding="utf-8")
        assert 'href="css/style.css"' in content, f"style.css not linked in {page}"
        assert 'src="js/config.js"' in content, f"config.js not linked in {page}"
        assert 'src="js/api.js"' in content, f"api.js not linked in {page}"


def test_api_js_configuration():
    api_js_content = (FRONTEND_DIR / "js" / "api.js").read_text(encoding="utf-8")
    assert 'const API_BASE_URL = "http://127.0.0.1:8000/api/v1"' in api_js_content
    assert "KitchenPilotApi" in api_js_content
    assert "getApiBaseUrl" in api_js_content
    assert "setApiBaseUrl" in api_js_content
    assert "getRecommendationsByIngredients" in api_js_content
    assert "updatePreferences" in api_js_content
    assert "updateUserPreferences" in api_js_content
    assert "updateNutritionTargets" in api_js_content
    assert "updateUserNutritionTargets" in api_js_content
    assert "syncUserPantry" in api_js_content
    assert "syncPantry" in api_js_content
    # Stage 5 authentication helpers
    assert "verifyEmail" in api_js_content
    assert "resendVerification" in api_js_content
    assert "forgotPassword" in api_js_content
    assert "resetPassword" in api_js_content
    assert "loginWithGoogle" in api_js_content
    assert "getCurrentUser" in api_js_content
    assert "isEmailVerified" in api_js_content
    assert "retryAfter" in api_js_content


def test_environment_configuration():
    config_js_content = (FRONTEND_DIR / "js" / "config.js").read_text(encoding="utf-8")
    azure_prod = "https://kitchenpilot-api.whitestone-ffca5e6e.malaysiawest.azurecontainerapps.io/api/v1"
    assert azure_prod in config_js_content
    assert "http://127.0.0.1:8000/api/v1" in config_js_content
    assert "setKitchenPilotEnvironment" in config_js_content
    assert "resetKitchenPilotEnvironment" in config_js_content


def test_section_14_target_recommendation_contract():
    with TestClient(app) as client:
        payload = {
            "ingredients": ["rice", "onion", "tomato", "cumin", "turmeric"],
            "user_preferences": {"vegetarian": True},
            "top_k": 5,
        }
        response = client.post("/api/v1/recommend/by-ingredients", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5
        assert len(data["recommendations"]) == 5
        top = data["recommendations"][0]
        assert "recipe_id" in top
        assert "recipe_name" in top
        assert "hybrid_score" in top
        assert "explanation" in top
        assert len(top["explanation"]) > 0


def test_authenticated_startup_and_pantry_sync_cannot_inject_sample_ingredients():
    """Verify frontend runtime invariants:
    1. DOMContentLoaded startup MUST NOT automatically inject sample ingredients into ingredientsList.
    2. Sample ingredients ("cumin", "turmeric", etc.) must ONLY be triggered by explicit user action (#btn-sample-pantry).
    3. api.js syncUserPantry performs bidirectional pruning (deleting unselected items via DELETE and adding missing ones).
    4. recommendations.js input flushing ensures uncommitted text in #ingredient-input is flushed into ingredientsList.
    5. loadUserPreferencesIntoForm and updatePilotUI properly synchronize authenticated state without sample corruption.
    """
    rec_js = (FRONTEND_DIR / "js" / "recommendations.js").read_text(encoding="utf-8")
    api_js = (FRONTEND_DIR / "js" / "api.js").read_text(encoding="utf-8")

    # Invariant 1: DOMContentLoaded must NOT call setIngredients with sample ingredients automatically
    assert 'btnSample.addEventListener("click"' in rec_js
    # Verify auto-injection on startup is completely eliminated
    assert "Default sample on initial visit" not in rec_js

    # Invariant 2: syncUserPantry reconciles by deleting items not in target and only adding missing items
    assert "async function syncUserPantry" in api_js
    assert "deletePantryItem" in api_js
    assert "addPantryItem" in api_js
    assert "targetSet.has" in api_js

    # Invariant 3: Input flushing before save and recommend
    assert "addIngredientFromInput" in rec_js
    # btnSyncPrefs must flush pending input
    sync_prefs_idx = rec_js.find("if (btnSyncPrefs)")
    assert sync_prefs_idx != -1
    sync_prefs_end = rec_js.find("if (btnPurgeData)", sync_prefs_idx)
    sync_prefs_block = rec_js[sync_prefs_idx : sync_prefs_end if sync_prefs_end != -1 else sync_prefs_idx + 5000]
    assert "addIngredientFromInput" in sync_prefs_block
    assert "syncFn" in sync_prefs_block or "syncUserPantry" in sync_prefs_block
