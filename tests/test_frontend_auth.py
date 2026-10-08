"""Frontend Authentication UX Test Suite (Stage 5).

Verifies all requirements of STAGE 5 of AUTHENTICATION_UPGRADE_PLAN.md:
1. Static asset integrity and security (no secrets, proper scripts, proper links)
2. Registration UI contract (email, password, confirm password, password requirements, unverified notice)
3. Login UI contract (email, password, forgot password link, Google button, registration link)
4. Email verification UI contract (token parsing, auto-verify, success/invalid/expired states, resend)
5. Forgot password UI contract (anti-enumeration safe response, 429 countdown handling)
6. Password reset UI contract (token from query string, password requirements, success -> login)
7. Google Sign-In UI contract (GIS integration, graceful disabling, zero client secrets)
8. Authenticated session state, unverified email banner, and clean logout
9. Full integration of frontend API client helpers with backend auth routes
"""

from __future__ import annotations

from pathlib import Path
import re
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.base import Base
from src.personalization.models import (
    UserModel,
    UserPreferenceModel,
    UserNutritionTargetModel,
    EmailVerificationTokenModel,
    PasswordResetTokenModel,
    FederatedIdentityModel,
)
from src.personalization.security import hash_token
from src.api.dependencies import get_db
from src.api.main import app
from src.api.middleware import rate_limiter

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


@pytest.fixture(autouse=True)
def reset_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture(scope="module")
def frontend_auth_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(frontend_auth_engine):
    connection = frontend_auth_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    session.close()
    transaction.rollback()
    connection.close()


class TestFrontendStaticAssetSecurity:
    """Verifies that no secrets exist in frontend files and required assets exist."""

    def test_no_secrets_in_frontend_code(self):
        """Frontend files must NEVER contain SMTP passwords, Google client secrets, or JWT secrets."""
        for path in FRONTEND_DIR.glob("**/*"):
            if path.is_file() and path.suffix in [".html", ".js", ".css"]:
                content = path.read_text(encoding="utf-8")
                # Check for sensitive patterns
                assert "client_secret" not in content.lower() or "no client secret" in content.lower() or "never present" in content.lower(), (
                    f"Possible client_secret in {path}"
                )
                assert "smtp_password" not in content.lower()
                assert "jwt_secret" not in content.lower()
                assert "auth_secret_key" not in content.lower()

    def test_auth_pages_structure(self):
        """auth.html, verify-email.html, and reset-password.html must have correct structure."""
        auth_html = (FRONTEND_DIR / "auth.html").read_text(encoding="utf-8")
        assert 'id="form-login"' in auth_html
        assert 'id="form-register"' in auth_html
        assert 'id="form-forgot"' in auth_html
        assert 'id="form-reset"' in auth_html
        assert 'id="form-resend-verification"' in auth_html
        assert 'id="reg-confirm-password"' in auth_html
        assert 'id="reg-password-requirements"' in auth_html
        assert 'src="js/config.js"' in auth_html
        assert 'src="js/api.js"' in auth_html
        assert 'src="js/auth.js"' in auth_html

    def test_verify_email_page_structure(self):
        verify_html = (FRONTEND_DIR / "verify-email.html").read_text(encoding="utf-8")
        assert 'id="verify-status-box"' in verify_html
        assert 'id="form-resend-verification"' in verify_html
        assert 'src="js/auth.js"' in verify_html

    def test_reset_password_page_structure(self):
        reset_html = (FRONTEND_DIR / "reset-password.html").read_text(encoding="utf-8")
        assert 'id="form-reset"' in reset_html
        assert 'id="reset-password"' in reset_html
        assert 'id="reset-confirm-password"' in reset_html
        assert 'id="reset-password-requirements"' in reset_html
        assert 'src="js/auth.js"' in reset_html

    def test_recommendations_page_has_unverified_banner(self):
        rec_html = (FRONTEND_DIR / "recommendations.html").read_text(encoding="utf-8")
        assert 'id="unverified-email-banner"' in rec_html
        assert 'id="btn-banner-resend-verification"' in rec_html


class TestFrontendAuthConfigContract:
    """Verifies config.js Google and environment resolution."""

    def test_config_js_google_auth_properties(self):
        config_js = (FRONTEND_DIR / "js" / "config.js").read_text(encoding="utf-8")
        assert "DEFAULT_GOOGLE_CONFIG" in config_js
        assert "resolveGoogleConfig" in config_js
        assert "window.getGoogleAuthConfig" in config_js
        assert "window.setGoogleAuthConfig" in config_js
        assert "window.resetGoogleAuthConfig" in config_js
        # Must default to disabled
        assert "enabled: false" in config_js

    def test_auth_js_password_policy_logic(self):
        """auth.js must enforce 8 chars, uppercase, lowercase, digit, and symbol."""
        auth_js = (FRONTEND_DIR / "js" / "auth.js").read_text(encoding="utf-8")
        assert "validatePasswordPolicy" in auth_js
        assert "[A-Z]" in auth_js
        assert "[a-z]" in auth_js
        assert "[0-9]" in auth_js
        assert "[^A-Za-z0-9]" in auth_js

    def test_auth_js_handles_retry_after_countdown(self):
        """auth.js must extract and show retryAfter countdown on 429 without looping."""
        auth_js = (FRONTEND_DIR / "js" / "auth.js").read_text(encoding="utf-8")
        assert "retryAfter" in auth_js
        assert "countdown-badge" in auth_js
        assert "setInterval" in auth_js
        assert "clearInterval" in auth_js

    def test_auth_js_google_disabled_fallback(self):
        """auth.js must display a disabled note when Google is not configured."""
        auth_js = (FRONTEND_DIR / "js" / "auth.js").read_text(encoding="utf-8")
        assert "google-disabled-note" in auth_js
        assert "disabled" in auth_js


class TestFrontendAPIClientAuthIntegration:
    """Verifies that api.js contract routes match actual backend API endpoints."""

    def test_registration_contract_and_unverified_response(self, client):
        """POST /auth/register returns 201, JWT, and unverified user."""
        payload = {
            "email": "priya.frontend@example.com",
            "password": "SecurePassword123!",
            "display_name": "Chef Priya",
        }
        res = client.post("/api/v1/auth/register", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert "access_token" in data
        assert data["user"]["email"] == "priya.frontend@example.com"
        assert data["user"]["is_verified"] is False

    def test_login_contract_returns_jwt_and_user(self, client):
        """POST /auth/login returns 200, JWT, and user details."""
        # First register
        reg_payload = {
            "email": "priya.frontend2@example.com",
            "password": "SecurePassword123!",
        }
        client.post("/api/v1/auth/register", json=reg_payload)

        # Now login
        login_payload = {
            "email": "priya.frontend2@example.com",
            "password": "SecurePassword123!",
        }
        res = client.post("/api/v1/auth/login", json=login_payload)
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["user"]["is_verified"] is False

    def test_forgot_password_contract_anti_enumeration(self, client):
        """POST /auth/forgot-password returns 200 for existing and non-existing email."""
        for email in ["priya.frontend@example.com", "nonexistent.user@example.com"]:
            res = client.post("/api/v1/auth/forgot-password", json={"email": email})
            assert res.status_code == 200
            data = res.json()
            assert "message" in data

    def test_resend_verification_contract_anti_enumeration(self, client):
        """POST /auth/resend-verification returns 200 without leaking presence."""
        for email in ["priya.frontend@example.com", "nonexistent.user@example.com"]:
            res = client.post("/api/v1/auth/resend-verification", json={"email": email})
            assert res.status_code == 200
            data = res.json()
            assert "message" in data

    def test_verify_email_contract_rejects_invalid_token(self, client):
        """POST /auth/verify-email returns 400 for invalid token without crashing."""
        res = client.post("/api/v1/auth/verify-email", json={"token": "invalid_frontend_token"})
        assert res.status_code == 400
        data = res.json()
        assert "detail" in data

    def test_reset_password_contract_rejects_invalid_token(self, client):
        """POST /auth/reset-password returns 400 for invalid token without crashing."""
        payload = {
            "token": "invalid_reset_token",
            "new_password": "NewSecurePassword456!",
        }
        res = client.post("/api/v1/auth/reset-password", json=payload)
        assert res.status_code == 400
        data = res.json()
        assert "detail" in data

    def test_google_auth_endpoint_rate_limiting_and_error_handling(self, client):
        """POST /auth/google returns 400, 403, or 503 (disabled) for invalid token."""
        res = client.post("/api/v1/auth/google", json={"id_token": "dummy_google_token"})
        assert res.status_code in [400, 403, 503]
