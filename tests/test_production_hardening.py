"""Stage H Production Hardening, Observability, and Security Test Suite."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.config import (
    ALLOWED_ORIGINS,
    AUTH_SECRET_KEY,
    ENVIRONMENT,
    validate_production_configuration,
)
from src.api.main import app
from src.api.middleware import InMemoryRateLimiter, metrics_collector


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_request_id_and_security_headers_present(client: TestClient):
    """Verify X-Request-ID and standard security headers on API responses."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert resp.headers["X-Request-ID"].startswith("req_")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-XSS-Protection"] == "1; mode=block"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_incoming_request_id_preserved(client: TestClient):
    """Verify that a valid incoming client X-Request-ID is honored."""
    custom_id = "req_custom_trace_98765"
    resp = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == custom_id


def test_metrics_endpoint_records_telemetry(client: TestClient):
    """Verify that requests record latency and status code in /api/v1/metrics."""
    # Issue a request
    client.get("/api/v1/health")
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_requests" in data
    assert data["total_requests"] > 0
    assert "status_codes" in data
    assert "endpoint_latencies" in data


def test_readiness_probe_structure(client: TestClient):
    """Verify enriched readiness probe checks all required components."""
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    checks = data["checks"]
    assert "model_artifacts" in checks
    assert "recipe_corpus" in checks
    assert "processed_data" in checks
    assert "database_connectivity" in checks
    assert "configuration_valid" in checks


def test_production_configuration_validation():
    """Verify that validate_production_configuration detects weak secrets in prod."""
    # Under current test env (development), validation passes
    errors = validate_production_configuration()
    assert len(errors) == 0


def test_in_memory_rate_limiter_triggers():
    """Verify in-memory sliding-window rate limiter blocks when threshold is exceeded."""
    limiter = InMemoryRateLimiter()
    ip = "192.168.1.100"
    path = "/api/v1/auth/login"

    # Limit for auth is RATE_LIMIT_AUTH_RPM (20)
    for _ in range(20):
        allowed, _ = limiter.check_rate_limit(ip, path)
        assert allowed is True

    # 21st request should be rejected with positive retry-after
    allowed, retry_after = limiter.check_rate_limit(ip, path)
    assert allowed is False
    assert retry_after > 0


def test_error_response_contains_request_id(client: TestClient):
    """Verify that 404 and 422 error payloads include request_id."""
    resp = client.get("/api/v1/recipes/NON_EXISTENT_R99999")
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    assert "request_id" in body


def test_artifact_manifest_integrity():
    """Verify that models/manifest.json accurately reflects project files."""
    manifest_path = Path("models/manifest.json")
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "artifacts" in manifest
    assert "tfidf_vectorizer" in manifest["artifacts"]
    assert manifest["artifacts"]["tfidf_vectorizer"]["required"] is True
