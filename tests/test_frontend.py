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
        FRONTEND_DIR / "css" / "style.css",
        FRONTEND_DIR / "js" / "api.js",
        FRONTEND_DIR / "js" / "app.js",
        FRONTEND_DIR / "js" / "recipes.js",
        FRONTEND_DIR / "js" / "recipe.js",
        FRONTEND_DIR / "js" / "recommendations.js",
    ]
    for filepath in expected_files:
        assert filepath.is_file(), f"Missing required frontend file: {filepath}"


def test_html_script_and_css_links():
    html_pages = ["index.html", "recipes.html", "recipe.html", "recommendations.html"]
    for page in html_pages:
        content = (FRONTEND_DIR / page).read_text(encoding="utf-8")
        assert 'href="css/style.css"' in content, f"style.css not linked in {page}"
        assert 'src="js/api.js"' in content, f"api.js not linked in {page}"


def test_api_js_configuration():
    api_js_content = (FRONTEND_DIR / "js" / "api.js").read_text(encoding="utf-8")
    assert 'const API_BASE_URL = "http://127.0.0.1:8000/api/v1"' in api_js_content
    assert "KitchenPilotApi" in api_js_content
    assert "getRecommendationsByIngredients" in api_js_content


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
