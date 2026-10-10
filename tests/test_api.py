"""Automated API Integration Tests for KitchenPilot-V1 FastAPI Backend.

Covers:
1. Health endpoint
2. Readiness endpoint
3. Recipe listing
4. Valid recipe retrieval
5. Invalid recipe ID -> 404
6. Nutrition endpoint
7. Recommendation endpoint
8. Ingredient recommendation endpoint
9. Similar recipe endpoint
10. Invalid top_k (< 1) -> 422
11. Top_k > 50 -> 422
12. Empty ingredient list handling
13. Unknown ingredient handling
14. Vegetarian filter
15. Excluded ingredients
16. Required ingredients
17. API does not modify frozen datasets
"""

from __future__ import annotations

import hashlib
import time
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from src.api.config import (
    RECIPE_NUTRITION_PATH,
    RECIPES_PATH,
    TFIDF_MATRIX_PATH,
    TFIDF_VECTORIZER_PATH,
)
from src.api.main import app


def _compute_sha256(filepath) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Module-scoped TestClient to load backend and models once across all tests."""
    with TestClient(app) as test_client:
        yield test_client


# 1. Health endpoint
def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "KitchenPilot-V1"
    assert data["version"] == "1.0.0"


# 2. Readiness endpoint
def test_readiness_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["model_artifacts"] is True
    assert data["checks"]["recipe_corpus"] is True
    assert data["checks"]["processed_data"] is True


# 3. Recipe listing
def test_recipe_listing(client: TestClient) -> None:
    response = client.get("/api/v1/recipes?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total"] < 6871
    assert data["total"] > 4000
    assert data["total_pages"] >= 400
    assert len(data["recipes"]) == 10
    first = data["recipes"][0]
    assert "recipe_id" in first
    assert "recipe_name" in first
    assert "vegetarian" in first


# 4. Valid recipe retrieval
def test_valid_recipe_retrieval(client: TestClient) -> None:
    response = client.get("/api/v1/recipes/R00006")
    assert response.status_code == 200
    data = response.json()
    assert data["recipe_id"] == "R00006"
    assert "Pongal" in data["recipe_name"]
    assert isinstance(data["ingredients"], list)
    assert len(data["ingredients"]) > 0
    assert data["instructions"] is not None
    assert "nutrition" in data
    assert data["nutrition"]["recipe_id"] == "R00006"


# 5. Invalid recipe ID -> 404
def test_invalid_recipe_id_404(client: TestClient) -> None:
    response = client.get("/api/v1/recipes/NON_EXISTENT_ID_99999")
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


# 6. Nutrition endpoint
def test_nutrition_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/recipes/R00006/nutrition")
    assert response.status_code == 200
    data = response.json()
    assert data["recipe_id"] == "R00006"
    assert data["calories"] is not None
    assert data["calories"] > 0
    assert data["protein"] is not None
    assert data["nutrition_quality"] is not None
    assert 0.0 <= data["nutrition_confidence"] <= 1.0

    # Test unknown recipe nutrition returns 404
    missing_response = client.get("/api/v1/recipes/INVALID_RECIPE_XYZ/nutrition")
    assert missing_response.status_code == 404


# 7. Recommendation endpoint
def test_recommendation_endpoint(client: TestClient) -> None:
    t0 = time.perf_counter()
    response = client.post(
        "/api/v1/recommend",
        json={
            "query_recipe_id": "R00006",
            "top_k": 5,
        },
    )
    latency_ms = (time.perf_counter() - t0) * 1000.0
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert len(data["recommendations"]) == 5
    first = data["recommendations"][0]
    assert first["rank"] == 1
    assert 0.0 <= first["hybrid_score"] <= 1.0
    assert first["recipe_id"] != "R00006"  # Input recipe excluded
    assert len(first["explanation"]) > 0
    # Performance assertion: sub-second on warmed model
    assert latency_ms < 2000.0


# 8. Ingredient recommendation endpoint
def test_ingredient_recommendation_endpoint(client: TestClient) -> None:
    response = client.post(
        "/api/v1/recommend/by-ingredients",
        json={
            "ingredients": ["rice", "onion", "tomato", "cumin", "turmeric"],
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert len(data["recommendations"]) == 5
    top_rec = data["recommendations"][0]
    assert len(top_rec["matched_ingredients"]) > 0
    assert 0.0 <= top_rec["ingredient_match_score"] <= 1.0


# 9. Similar recipe endpoint
def test_similar_recipe_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/recipes/R00006/similar?top_k=5")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert len(data["recommendations"]) == 5
    rec_ids = [r["recipe_id"] for r in data["recommendations"]]
    assert "R00006" not in rec_ids

    # Unknown recipe ID returns 404
    invalid_resp = client.get("/api/v1/recipes/UNKNOWN_ID/similar")
    assert invalid_resp.status_code == 404


# 10. Invalid top_k (< 1) -> 422
def test_invalid_top_k_under_one(client: TestClient) -> None:
    response = client.post(
        "/api/v1/recommend",
        json={
            "available_ingredients": ["rice"],
            "top_k": 0,
        },
    )
    assert response.status_code == 422


# 11. Top_k > 50 -> 422
def test_invalid_top_k_over_fifty(client: TestClient) -> None:
    response = client.post(
        "/api/v1/recommend",
        json={
            "available_ingredients": ["rice"],
            "top_k": 51,
        },
    )
    assert response.status_code == 422

    # Query param validation on similar
    sim_resp = client.get("/api/v1/recipes/R00006/similar?top_k=51")
    assert sim_resp.status_code == 422


# 12. Empty ingredient list handling
def test_empty_ingredient_list_handling(client: TestClient) -> None:
    response = client.post(
        "/api/v1/recommend",
        json={
            "available_ingredients": [],
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5


# 13. Unknown ingredient handling
def test_unknown_ingredient_handling(client: TestClient) -> None:
    response = client.post(
        "/api/v1/recommend",
        json={
            "available_ingredients": ["xyznonexistentingredient12345", "anotherfakespice999"],
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    for item in data["recommendations"]:
        assert 0.0 <= item["hybrid_score"] <= 1.0


# 14. Vegetarian filter
def test_vegetarian_filter(client: TestClient) -> None:
    response = client.post(
        "/api/v1/recommend",
        json={
            "available_ingredients": ["rice", "tomato"],
            "user_preferences": {"vegetarian": True},
            "top_k": 10,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 0
    # Cross-verify each recommended recipe is vegetarian in catalog
    for item in data["recommendations"]:
        rec_detail = client.get(f"/api/v1/recipes/{item['recipe_id']}").json()
        assert rec_detail["vegetarian"] is True


# 15. Excluded ingredients
def test_excluded_ingredients_respected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/recommend",
        json={
            "available_ingredients": ["rice", "cumin"],
            "user_preferences": {
                "excluded_ingredients": ["onion", "garlic"]
            },
            "top_k": 10,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 0
    for item in data["recommendations"]:
        rec_detail = client.get(f"/api/v1/recipes/{item['recipe_id']}").json()
        ing_text = " ".join(rec_detail["ingredients"]).lower()
        assert "onion" not in ing_text, f"Excluded 'onion' found in {item['recipe_id']}"
        assert "garlic" not in ing_text, f"Excluded 'garlic' found in {item['recipe_id']}"


# 16. Required ingredients
def test_required_ingredients_handled(client: TestClient) -> None:
    response = client.post(
        "/api/v1/recommend",
        json={
            "available_ingredients": ["rice", "salt", "water"],
            "user_preferences": {
                "required_ingredients": ["rice"]
            },
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 0
    for item in data["recommendations"]:
        assert "rice" in item["matched_ingredients"]


# 17. API does not modify frozen datasets
def test_frozen_datasets_immutability(client: TestClient) -> None:
    recipes_sha_before = _compute_sha256(RECIPES_PATH)
    nutrition_sha_before = _compute_sha256(RECIPE_NUTRITION_PATH)
    tfidf_sha_before = _compute_sha256(TFIDF_MATRIX_PATH)

    # Perform various read and recommendation requests
    client.get("/api/v1/recipes/R00001")
    client.get("/api/v1/recipes/R00001/nutrition")
    client.post(
        "/api/v1/recommend",
        json={"available_ingredients": ["rice", "tomato"], "top_k": 5},
    )

    recipes_sha_after = _compute_sha256(RECIPES_PATH)
    nutrition_sha_after = _compute_sha256(RECIPE_NUTRITION_PATH)
    tfidf_sha_after = _compute_sha256(TFIDF_MATRIX_PATH)

    assert recipes_sha_before == recipes_sha_after, "recipes.csv was modified!"
    assert nutrition_sha_before == nutrition_sha_after, "recipe_nutrition.csv was modified!"
    assert tfidf_sha_before == tfidf_sha_after, "TF-IDF matrix was modified!"
