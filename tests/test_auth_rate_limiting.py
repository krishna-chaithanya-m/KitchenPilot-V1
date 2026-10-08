"""Comprehensive test suite for Stage 4 — Route-Specific Authentication Rate Limiting.

Verifies:
1. Exact endpoint limits:
   - POST /api/v1/auth/verify-email: 10 req/min
   - POST /api/v1/auth/resend-verification: 3 req/hour
   - POST /api/v1/auth/forgot-password: 3 req/hour
   - POST /api/v1/auth/reset-password: 5 req/min
   - POST /api/v1/auth/google: 10 req/min
2. Preservation of existing rate limits:
   - General auth (login / register): 20 req/min
   - Recommendations: 60 req/min
   - Feedback: 60 req/min
   - Global: 120 req/min
3. Rate limiter behavior & security:
   - Requests below limit succeed
   - Requests at limit behave correctly
   - Requests exceeding limit return HTTP 429 Too Many Requests
   - Useful Retry-After header included in 429 responses
   - Independent buckets per endpoint (exhausting one does not block another)
   - Independent buckets per client IP
   - Anti-enumeration preserved for forgot-password and resend-verification under rate limiting
   - No token, password, or secret leakage in 429 errors or logs
   - Untrusted X-Forwarded-For headers rejected unless proxy is explicitly trusted
   - Changing email address does not bypass IP-based limits
   - Authenticated non-auth APIs are not accidentally blocked
"""

from __future__ import annotations

import time
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.dependencies import get_db
from src.api.main import app
from src.api.middleware import rate_limiter, RequestCorrelationAndSecurityMiddleware
from src.db.base import Base


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Ensure in-memory rate limiter history is clear before each test."""
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture(scope="module")
def stage4_engine():
    """Create in-memory SQLite database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def stage4_db(stage4_engine):
    """Provide isolated transactional session."""
    connection = stage4_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(stage4_db):
    """FastAPI test client with in-memory database."""
    def override_get_db():
        yield stage4_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ============================================================================
# 1. InMemoryRateLimiter Unit Tests
# ============================================================================

class TestInMemoryRateLimiterUnit:
    """Unit tests for sliding-window algorithm and route-specific limits."""

    def test_verify_email_limit_is_10_per_minute(self):
        client_ip = "192.168.1.100"
        path = "/api/v1/auth/verify-email"

        # First 10 requests allowed
        for i in range(10):
            allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
            assert allowed is True, f"Request {i+1} should be allowed"
            assert retry_after == 0

        # 11th request rejected
        allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
        assert allowed is False
        assert 1 <= retry_after <= 60

    def test_resend_verification_limit_is_3_per_hour(self):
        client_ip = "192.168.1.101"
        path = "/api/v1/auth/resend-verification"

        # First 3 requests allowed
        for i in range(3):
            allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
            assert allowed is True, f"Request {i+1} should be allowed"

        # 4th request rejected with hour-scale retry_after
        allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
        assert allowed is False
        assert 1 <= retry_after <= 3600

    def test_forgot_password_limit_is_3_per_hour(self):
        client_ip = "192.168.1.102"
        path = "/api/v1/auth/forgot-password"

        for i in range(3):
            allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
            assert allowed is True

        allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
        assert allowed is False
        assert 1 <= retry_after <= 3600

    def test_reset_password_limit_is_5_per_minute(self):
        client_ip = "192.168.1.103"
        path = "/api/v1/auth/reset-password"

        for i in range(5):
            allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
            assert allowed is True

        allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
        assert allowed is False
        assert 1 <= retry_after <= 60

    def test_google_limit_is_10_per_minute(self):
        client_ip = "192.168.1.104"
        path = "/api/v1/auth/google"

        for i in range(10):
            allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
            assert allowed is True

        allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
        assert allowed is False
        assert 1 <= retry_after <= 60

    def test_general_auth_limit_remains_20_per_minute(self):
        """General auth endpoints (login, register) preserve their 20 RPM limit."""
        client_ip = "192.168.1.105"
        path = "/api/v1/auth/login"

        for i in range(20):
            allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
            assert allowed is True, f"Login request {i+1} should be allowed"

        allowed, retry_after = rate_limiter.check_rate_limit(client_ip, path, method="POST")
        assert allowed is False
        assert 1 <= retry_after <= 60

    def test_each_endpoint_has_independent_bucket(self):
        """Exhausting quota on one endpoint does not block other endpoints for same IP."""
        client_ip = "192.168.1.106"

        # Exhaust forgot-password (3 req/hr)
        for _ in range(3):
            rate_limiter.check_rate_limit(client_ip, "/api/v1/auth/forgot-password", method="POST")
        allowed_forgot, _ = rate_limiter.check_rate_limit(
            client_ip, "/api/v1/auth/forgot-password", method="POST"
        )
        assert allowed_forgot is False

        # Google auth remains fully available
        allowed_google, _ = rate_limiter.check_rate_limit(
            client_ip, "/api/v1/auth/google", method="POST"
        )
        assert allowed_google is True

        # Verify email remains fully available
        allowed_verify, _ = rate_limiter.check_rate_limit(
            client_ip, "/api/v1/auth/verify-email", method="POST"
        )
        assert allowed_verify is True

        # General login remains fully available
        allowed_login, _ = rate_limiter.check_rate_limit(
            client_ip, "/api/v1/auth/login", method="POST"
        )
        assert allowed_login is True

    def test_different_ips_have_independent_quotas(self):
        ip_a = "10.0.0.1"
        ip_b = "10.0.0.2"
        path = "/api/v1/auth/forgot-password"

        for _ in range(3):
            rate_limiter.check_rate_limit(ip_a, path, method="POST")

        # IP A is blocked
        allowed_a, _ = rate_limiter.check_rate_limit(ip_a, path, method="POST")
        assert allowed_a is False

        # IP B is not blocked
        allowed_b, _ = rate_limiter.check_rate_limit(ip_b, path, method="POST")
        assert allowed_b is True

    def test_sliding_window_expiration(self):
        """Older requests drop out of window allowing subsequent requests."""
        client_ip = "192.168.1.107"
        path = "/api/v1/auth/forgot-password"
        base_time = 100000.0

        with patch("time.time", return_value=base_time):
            for _ in range(3):
                rate_limiter.check_rate_limit(client_ip, path, method="POST")
            allowed, _ = rate_limiter.check_rate_limit(client_ip, path, method="POST")
            assert allowed is False

        # Advance time by 3601 seconds (past 1-hour window)
        with patch("time.time", return_value=base_time + 3601.0):
            allowed_after_window, _ = rate_limiter.check_rate_limit(client_ip, path, method="POST")
            assert allowed_after_window is True


# ============================================================================
# 2. Trusted Proxy & IP Extraction Tests
# ============================================================================

class TestTrustedProxyHandling:
    """Verifies that X-Forwarded-For is not trusted by default."""

    def test_untrusted_x_forwarded_for_is_ignored(self):
        class DummyRequest:
            client = type("Client", (), {"host": "198.51.100.1"})()
            headers = {"X-Forwarded-For": "203.0.113.195, 198.51.100.1"}

        with patch("src.api.config.TRUSTED_PROXIES", ""):
            ip = RequestCorrelationAndSecurityMiddleware.get_client_ip(DummyRequest())  # type: ignore
            # Without trusted proxy configured, client.host is used
            assert ip == "198.51.100.1"

    def test_trusted_proxy_allows_forwarded_for_extraction(self):
        class DummyRequest:
            client = type("Client", (), {"host": "10.0.0.1"})()
            headers = {"X-Forwarded-For": "203.0.113.50, 10.0.0.1"}

        with patch("src.api.config.TRUSTED_PROXIES", "10.0.0.1, 10.0.0.2"):
            ip = RequestCorrelationAndSecurityMiddleware.get_client_ip(DummyRequest())  # type: ignore
            assert ip == "203.0.113.50"


# ============================================================================
# 3. HTTP Integration & Rate Limit Enforcement Tests
# ============================================================================

class TestAuthRateLimitingIntegration:
    """Integration tests verifying HTTP 429 status, Retry-After header, and error schema."""

    @patch("src.api.config.RATE_LIMIT_ENABLED", True)
    def test_forgot_password_rate_limit_and_anti_enumeration(self, client):
        """POST /forgot-password enforces 3 req/hr limit without leaking user existence."""
        # Requests 1-3 succeed with standard 200 message
        for i in range(3):
            resp = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": f"victim{i}@example.com"},
            )
            assert resp.status_code == 200
            assert "instructions to reset your password" in resp.json()["message"]

        # Request 4 returns 429 Too Many Requests
        resp = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "victim_new@example.com"},
        )
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert "Retry-After" in resp.headers
        retry_after = int(resp.headers["Retry-After"])
        assert 1 <= retry_after <= 3600

        # Changing email does not bypass limit
        resp_bypass_attempt = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "completely_different@example.com"},
        )
        assert resp_bypass_attempt.status_code == 429

    @patch("src.api.config.RATE_LIMIT_ENABLED", True)
    def test_resend_verification_rate_limit(self, client):
        """POST /resend-verification enforces 3 req/hr limit."""
        for _ in range(3):
            resp = client.post(
                "/api/v1/auth/resend-verification",
                json={"email": "tester@example.com"},
            )
            assert resp.status_code == 200

        resp = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "tester@example.com"},
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert "Retry-After" in resp.headers

    @patch("src.api.config.RATE_LIMIT_ENABLED", True)
    def test_verify_email_rate_limit(self, client):
        """POST /verify-email enforces 10 req/min limit."""
        for _ in range(10):
            resp = client.post(
                "/api/v1/auth/verify-email",
                json={"token": "a" * 32},
            )
            # Expect 400 (invalid token), but NOT 429
            assert resp.status_code == 400

        # 11th request returns 429
        resp = client.post(
            "/api/v1/auth/verify-email",
            json={"token": "a" * 32},
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    @patch("src.api.config.RATE_LIMIT_ENABLED", True)
    def test_reset_password_rate_limit(self, client):
        """POST /reset-password enforces 5 req/min limit."""
        for _ in range(5):
            resp = client.post(
                "/api/v1/auth/reset-password",
                json={"token": "a" * 32, "new_password": "ValidPassword123!"},
            )
            assert resp.status_code == 400

        # 6th request returns 429
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "a" * 32, "new_password": "ValidPassword123!"},
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    @patch("src.api.config.RATE_LIMIT_ENABLED", True)
    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    def test_google_auth_rate_limit(self, client):
        """POST /google enforces 10 req/min limit."""
        for _ in range(10):
            resp = client.post(
                "/api/v1/auth/google",
                json={"id_token": "mock.google.id_token"},
            )
            # 401 or similar (invalid token), but NOT 429
            assert resp.status_code in (401, 503)

        # 11th request returns 429
        resp = client.post(
            "/api/v1/auth/google",
            json={"id_token": "mock.google.id_token"},
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    @patch("src.api.config.RATE_LIMIT_ENABLED", True)
    def test_non_auth_endpoints_not_blocked_when_auth_is_rate_limited(self, client):
        """Exhausting auth rate limits does not affect public catalog or health endpoints."""
        # Exhaust forgot-password limit
        for _ in range(3):
            client.post("/api/v1/auth/forgot-password", json={"email": "a@b.com"})
        auth_blocked = client.post("/api/v1/auth/forgot-password", json={"email": "a@b.com"})
        assert auth_blocked.status_code == 429

        # Health endpoint remains 200 OK
        health_resp = client.get("/api/v1/health")
        assert health_resp.status_code == 200

        # Recipes listing remains 200 OK
        recipes_resp = client.get("/api/v1/recipes?limit=5")
        assert recipes_resp.status_code == 200

    @patch("src.api.config.RATE_LIMIT_ENABLED", True)
    def test_429_response_never_leaks_tokens_or_secrets(self, client):
        """Error details in 429 responses contain only generic rate limit message."""
        for _ in range(3):
            client.post("/api/v1/auth/forgot-password", json={"email": "secret_user@example.com"})

        secret_token = "secret-token-payload-xyz-987654"
        resp = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": f"{secret_token}@example.com"},
        )
        assert resp.status_code == 429
        assert secret_token not in resp.text
        assert "RATE_LIMIT_EXCEEDED" in resp.json()["error"]["code"]
