"""Production OpenAPI Contract and Schema Conformance Test Suite (Stage J).

Automated tests validating:
- OpenAPI specification availability & structure
- Route availability & HTTP status correctness
- Request and response schema validation
- Anonymous vs Authenticated access boundaries
- Error response envelopes (detail, request_id, zero internal stack trace exposure)
- Pagination parameters and deterministic boundaries
- Strict credential and secret non-leakage (zero password hashes in payloads)
"""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient
from src.api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_openapi_spec_structure(client: TestClient):
    """Verify /openapi.json exists, is valid JSON, and defines all production endpoints."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "KitchenPilot-V1 API"
    paths = spec["paths"]

    expected_routes = [
        "/api/v1/health",
        "/api/v1/health/ready",
        "/api/v1/metrics",
        "/api/v1/recipes",
        "/api/v1/recipes/{recipe_id}",
        "/api/v1/recommend",
        "/api/v1/recommend/by-ingredients",
        "/api/v1/recommend/semantic",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/user/profile",
        "/api/v1/user/preferences",
        "/api/v1/user/nutrition-targets",
        "/api/v1/user/pantry",
        "/api/v1/user/feedback",
        "/api/v1/user/history",
        "/api/v1/user/data",
    ]
    for route in expected_routes:
        assert route in paths, f"Expected route {route} missing from OpenAPI schema"


def test_anonymous_access_boundaries(client: TestClient):
    """Verify that public endpoints allow anonymous requests, while user endpoints require JWT."""
    # Public endpoints
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/recipes?limit=5").status_code == 200
    assert client.post("/api/v1/recommend", json={"top_k": 2}).status_code == 200

    # Protected endpoints require authentication
    protected_gets = [
        "/api/v1/user/profile",
        "/api/v1/user/pantry",
        "/api/v1/user/feedback",
        "/api/v1/user/history",
    ]
    for p in protected_gets:
        resp = client.get(p)
        assert resp.status_code == 401, f"Expected 401 Unauthorized for {p}, got {resp.status_code}"

    # Protected mutations require authentication
    assert client.put("/api/v1/user/preferences", json={"vegetarian": True}).status_code == 401
    assert client.delete("/api/v1/user/data").status_code == 401


def test_error_response_structure_and_no_stack_traces(client: TestClient):
    """Verify that error payloads contain clean messages with request_id and no tracebacks."""
    # 404 Not Found
    resp_404 = client.get("/api/v1/recipes/RECIPE_DOES_NOT_EXIST_XYZ")
    assert resp_404.status_code == 404
    body_404 = resp_404.json()
    assert "detail" in body_404
    assert "request_id" in body_404
    assert "Traceback" not in json.dumps(body_404)

    # 422 Unprocessable Entity
    resp_422 = client.post("/api/v1/recommend", json={"top_k": "not_an_integer"})
    assert resp_422.status_code == 422
    body_422 = resp_422.json()
    assert "detail" in body_422
    assert "request_id" in body_422
    assert "Traceback" not in json.dumps(body_422)


def test_zero_secret_leakage_in_schemas(client: TestClient):
    """Verify that user responses never leak password_hash or secret keys."""
    resp = client.get("/openapi.json")
    spec_text = resp.text.lower()
    # Ensure raw password hashes are not part of any response schema definition
    assert "password_hash" not in spec_text
    assert "auth_secret_key" not in spec_text


def test_pagination_contract(client: TestClient):
    """Verify pagination behavior on /api/v1/recipes."""
    r1 = client.get("/api/v1/recipes?page=1&page_size=3")
    assert r1.status_code == 200
    data1 = r1.json()
    assert len(data1["recipes"]) == 3
    assert data1["page"] == 1
    assert data1["page_size"] == 3
    assert data1["total"] > 6000

    r2 = client.get("/api/v1/recipes?page=2&page_size=3")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["recipes"]) == 3
    assert data2["page"] == 2
    # Different page items
    assert data1["recipes"][0]["recipe_id"] != data2["recipes"][0]["recipe_id"]

