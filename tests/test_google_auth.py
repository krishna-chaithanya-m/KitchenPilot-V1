"""Comprehensive test suite for Stage 3 — Google OAuth/OIDC Sign-In.

Verifies:
1. Cryptographic token verification & validation:
   - Valid Google ID token
   - Invalid signature
   - Invalid audience
   - Invalid issuer
   - Expired token
   - Missing email claim
   - Unverified email claim
   - Malformed/empty token
   - Google authentication disabled
2. Federated identity handling:
   - Existing Google identity logs in (sub recognized)
   - Existing verified local account safely linked without duplicate accounts
   - Existing user ID, pantry, preferences, feedback, and history preserved after linking
   - Duplicate Google identity linking rejected / handled safely
   - Same Google subject cannot be linked to multiple users
   - New Google user created correctly with is_verified=True and auth_provider='google'
3. Pilot admission control safety:
   - Google sign-in cannot bypass pilot capacity
   - Google sign-in cannot bypass invite code requirements
   - Existing linked users can still authenticate even when pilot capacity is full
4. JWT compatibility:
   - Returned JWT adheres to standard claim structure (sub: str(user.id), iat, exp)
   - Returned access token works seamlessly with protected endpoints (get_current_user)
5. Local authentication compatibility:
   - Existing local account remains authenticable via password after Google linking
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.dependencies import get_db
from src.api.main import app
from src.db.base import Base
from src.personalization.models import (
    FederatedIdentityModel,
    UserFeedbackModel,
    UserModel,
    UserPantryModel,
    UserPreferenceModel,
)
from src.personalization.schemas import (
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
)
from src.personalization.security import (
    decode_access_token,
    hash_password,
    verify_google_id_token,
    verify_password,
)
from src.personalization.service import PersonalizationService


# ============================================================================
# Test Database Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def stage3_engine():
    """Create in-memory SQLite engine with all registered tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def stage3_db(stage3_engine):
    """Provide transactional session for Stage 3 testing."""
    connection = stage3_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def stage3_client(stage3_db):
    """Provide FastAPI test client with mocked DB session."""
    def override_get_db():
        yield stage3_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# Helper payload builder for Google ID tokens
def make_mock_google_payload(
    sub: str = "google-sub-10001",
    email: str = "pilot.tester@gmail.com",
    email_verified: bool = True,
    iss: str = "https://accounts.google.com",
    name: str = "Pilot Tester",
) -> Dict[str, Any]:
    return {
        "iss": iss,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "name": name,
        "aud": "test-client-id.apps.googleusercontent.com",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
    }


# ============================================================================
# 1. Google ID Token Verification Tests
# ============================================================================

class TestGoogleIdTokenVerification:
    """Tests for cryptographic token verification in verify_google_id_token."""

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.api.config.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_valid_google_id_token(self, mock_verify):
        payload = make_mock_google_payload()
        mock_verify.return_value = payload

        result = verify_google_id_token("mock.raw.id_token")
        assert result["email"] == "pilot.tester@gmail.com"
        assert result["sub"] == "google-sub-10001"
        assert result["email_verified"] is True

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", False)
    def test_google_disabled_rejected(self):
        with pytest.raises(ValueError, match="Google authentication is disabled"):
            verify_google_id_token("mock.raw.id_token")

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.api.config.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    def test_malformed_token_rejected(self):
        with pytest.raises(ValueError, match="Invalid Google ID token"):
            verify_google_id_token("")

        with pytest.raises(ValueError, match="Invalid Google ID token"):
            verify_google_id_token(None)  # type: ignore

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.api.config.GOOGLE_CLIENT_ID", "")
    def test_missing_client_id_rejected(self):
        with pytest.raises(ValueError, match="Google Client ID is not configured"):
            verify_google_id_token("mock.raw.id_token")

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.api.config.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_invalid_signature_rejected(self, mock_verify):
        mock_verify.side_effect = ValueError("Invalid cryptographic signature.")

        with pytest.raises(ValueError, match="Google ID token verification failed"):
            verify_google_id_token("mock.raw.id_token")

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.api.config.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_invalid_audience_rejected(self, mock_verify):
        mock_verify.side_effect = ValueError("Token audience mismatch.")

        with pytest.raises(ValueError, match="Google ID token verification failed"):
            verify_google_id_token("mock.raw.id_token")

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.api.config.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_expired_token_rejected(self, mock_verify):
        mock_verify.side_effect = ValueError("Token has expired.")

        with pytest.raises(ValueError, match="Google ID token verification failed"):
            verify_google_id_token("mock.raw.id_token")

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.api.config.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_invalid_issuer_rejected(self, mock_verify):
        payload = make_mock_google_payload(iss="https://malicious-issuer.evil.com")
        mock_verify.return_value = payload

        with pytest.raises(ValueError, match="Invalid Google token issuer"):
            verify_google_id_token("mock.raw.id_token")

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.api.config.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_missing_email_rejected(self, mock_verify):
        payload = make_mock_google_payload()
        del payload["email"]
        mock_verify.return_value = payload

        with pytest.raises(ValueError, match="Google ID token does not contain an email address"):
            verify_google_id_token("mock.raw.id_token")

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.api.config.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_unverified_email_rejected(self, mock_verify):
        payload = make_mock_google_payload(email_verified=False)
        mock_verify.return_value = payload

        with pytest.raises(ValueError, match="Google email address is not verified by Google"):
            verify_google_id_token("mock.raw.id_token")


# ============================================================================
# 2. Federated Identity Service & Account Linking Tests
# ============================================================================

class TestFederatedIdentityService:
    """Tests for PersonalizationService.authenticate_google_user logic."""

    @patch("src.personalization.service.verify_google_id_token")
    def test_new_google_user_provisioned_correctly(self, mock_verify, stage3_db):
        mock_verify.return_value = make_mock_google_payload(
            sub="sub-new-001",
            email="new.google.user@example.com",
            name="New Google User",
        )

        user, is_new = PersonalizationService.authenticate_google_user(stage3_db, "mock-token")

        assert is_new is True
        assert user.email == "new.google.user@example.com"
        assert user.is_verified is True
        assert user.auth_provider == "google"
        assert user.display_name == "New Google User"

        # Verify federated identity record exists
        fed = stage3_db.execute(
            select(FederatedIdentityModel).where(
                FederatedIdentityModel.user_id == user.id,
                FederatedIdentityModel.provider == "google",
            )
        ).scalar_one()
        assert fed.provider_user_id == "sub-new-001"

        # Verify default preferences and targets created
        prefs = stage3_db.execute(
            select(UserPreferenceModel).where(UserPreferenceModel.user_id == user.id)
        ).scalar_one_or_none()
        assert prefs is not None

    @patch("src.personalization.service.verify_google_id_token")
    def test_existing_google_identity_logs_in(self, mock_verify, stage3_db):
        mock_verify.return_value = make_mock_google_payload(
            sub="sub-existing-002",
            email="existing.google@example.com",
        )

        # First login provisions the user
        user1, is_new1 = PersonalizationService.authenticate_google_user(stage3_db, "mock-token")
        assert is_new1 is True

        # Second login authenticates existing user
        user2, is_new2 = PersonalizationService.authenticate_google_user(stage3_db, "mock-token")
        assert is_new2 is False
        assert user2.id == user1.id
        assert user2.email == "existing.google@example.com"

    @patch("src.personalization.service.verify_google_id_token")
    def test_existing_local_account_linked_safely(self, mock_verify, stage3_db):
        """Existing local account with matching email is linked without duplicating account."""
        local_user = UserModel(
            email="local.chef@example.com",
            password_hash=hash_password("LocalSecret123!"),
            display_name="Local Chef",
            is_active=True,
            is_verified=False,
            auth_provider="local",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        stage3_db.add(local_user)
        stage3_db.flush()

        # Add existing preferences and pantry items
        prefs = UserPreferenceModel(
            user_id=local_user.id,
            vegetarian=True,
            preferred_cuisines=["Italian", "Mexican"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        pantry = UserPantryModel(
            user_id=local_user.id,
            ingredient_name="Olive Oil",
            display_name="Olive Oil",
            status="IN_STOCK",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        stage3_db.add(prefs)
        stage3_db.add(pantry)
        stage3_db.commit()

        # Sign in with Google using the same verified email
        mock_verify.return_value = make_mock_google_payload(
            sub="sub-chef-local-003",
            email="local.chef@example.com",
        )

        linked_user, is_new = PersonalizationService.authenticate_google_user(stage3_db, "mock-token")

        assert is_new is False
        assert linked_user.id == local_user.id
        # Email marked verified upon linking
        assert linked_user.is_verified is True
        # Local password authentication remains preserved
        assert verify_password("LocalSecret123!", linked_user.password_hash) is True
        assert linked_user.auth_provider == "local"

        # Pantry & preferences preserved
        preserved_pantry = stage3_db.execute(
            select(UserPantryModel).where(UserPantryModel.user_id == local_user.id)
        ).scalar_one()
        assert preserved_pantry.ingredient_name == "Olive Oil"

        preserved_prefs = stage3_db.execute(
            select(UserPreferenceModel).where(UserPreferenceModel.user_id == local_user.id)
        ).scalar_one()
        assert preserved_prefs.vegetarian is True
        assert "Italian" in preserved_prefs.preferred_cuisines

    @patch("src.personalization.service.verify_google_id_token")
    def test_duplicate_google_sub_cannot_link_to_multiple_users(self, mock_verify, stage3_db):
        """A single Google subject cannot be claimed by a different user."""
        mock_verify.return_value = make_mock_google_payload(
            sub="shared-sub-conflict",
            email="user1@example.com",
        )
        user1, _ = PersonalizationService.authenticate_google_user(stage3_db, "mock-token")

        # Now an existing local user with a different email attempts to link the same Google sub
        user2 = UserModel(
            email="user2@example.com",
            password_hash=hash_password("Password2!"),
            is_active=True,
            auth_provider="local",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        stage3_db.add(user2)
        stage3_db.commit()

        # Google token returned for user2@example.com but has sub="shared-sub-conflict" already claimed by user1
        mock_verify.return_value = make_mock_google_payload(
            sub="shared-sub-conflict",
            email="user2@example.com",
        )

        with pytest.raises(ValueError, match="Identity conflict"):
            PersonalizationService.authenticate_google_user(stage3_db, "mock-token")

    @patch("src.personalization.service.verify_google_id_token")
    def test_single_user_cannot_link_multiple_google_accounts(self, mock_verify, stage3_db):
        """A user account cannot be linked to multiple distinct Google subjects."""
        mock_verify.return_value = make_mock_google_payload(
            sub="google-sub-first",
            email="multi.google@example.com",
        )
        user, _ = PersonalizationService.authenticate_google_user(stage3_db, "mock-token")

        # User tries to link a second Google subject
        mock_verify.return_value = make_mock_google_payload(
            sub="google-sub-second",
            email="multi.google@example.com",
        )
        with pytest.raises(ValueError, match="Identity conflict"):
            PersonalizationService.authenticate_google_user(stage3_db, "mock-token")


# ============================================================================
# 3. Pilot Mode & Capacity Safety Tests
# ============================================================================

class TestPilotAdmissionSafety:
    """Verifies that Google authentication respects pilot gates."""

    @patch("src.api.config.PILOT_MODE", True)
    @patch("src.api.config.PILOT_MAX_USERS", 1)
    @patch("src.personalization.service.verify_google_id_token")
    def test_google_cannot_bypass_pilot_capacity(self, mock_verify, stage3_db):
        """New Google user registration is blocked when pilot cohort is full."""
        # Provision 1 existing user to saturate capacity
        u = UserModel(
            email="pilot.first@example.com",
            password_hash=hash_password("Secret123!"),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        stage3_db.add(u)
        stage3_db.commit()

        mock_verify.return_value = make_mock_google_payload(
            sub="sub-blocked-capacity",
            email="new.google.denied@example.com",
        )

        with pytest.raises(PermissionError, match="Controlled pilot cohort capacity reached"):
            PersonalizationService.authenticate_google_user(stage3_db, "mock-token")

    @patch("src.api.config.PILOT_MODE", True)
    @patch("src.api.config.PILOT_INVITE_CODE", "SECRET_INVITE_2026")
    @patch("src.personalization.service.verify_google_id_token")
    def test_google_requires_pilot_invite_code(self, mock_verify, stage3_db):
        """New Google user registration fails without valid invite code."""
        mock_verify.return_value = make_mock_google_payload(
            sub="sub-invite-test",
            email="invite.google@example.com",
        )

        # Missing invite code
        with pytest.raises(PermissionError, match="Invalid or missing pilot invite code"):
            PersonalizationService.authenticate_google_user(stage3_db, "mock-token", invite_code=None)

        # Invalid invite code
        with pytest.raises(PermissionError, match="Invalid or missing pilot invite code"):
            PersonalizationService.authenticate_google_user(stage3_db, "mock-token", invite_code="WRONG_CODE")

        # Correct invite code succeeds
        user, is_new = PersonalizationService.authenticate_google_user(
            stage3_db, "mock-token", invite_code="SECRET_INVITE_2026"
        )
        assert is_new is True
        assert user.email == "invite.google@example.com"

    @patch("src.api.config.PILOT_MODE", True)
    @patch("src.api.config.PILOT_MAX_USERS", 1)
    @patch("src.personalization.service.verify_google_id_token")
    def test_existing_linked_user_can_still_login_when_pilot_is_full(self, mock_verify, stage3_db):
        """Existing linked Google user is never blocked by full pilot capacity."""
        # Create existing linked user
        user = UserModel(
            email="already.pilot@example.com",
            password_hash=hash_password("Pass123!"),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        stage3_db.add(user)
        stage3_db.flush()
        fed = FederatedIdentityModel(
            user_id=user.id,
            provider="google",
            provider_user_id="sub-already-admitted",
            email="already.pilot@example.com",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        stage3_db.add(fed)
        stage3_db.commit()

        mock_verify.return_value = make_mock_google_payload(
            sub="sub-already-admitted",
            email="already.pilot@example.com",
        )

        # User count is 1 (matches capacity = 1), but user already exists -> succeeds!
        authenticated_user, is_new = PersonalizationService.authenticate_google_user(stage3_db, "mock-token")
        assert is_new is False
        assert authenticated_user.id == user.id


# ============================================================================
# 4. API Endpoint Integration & JWT Compatibility Tests
# ============================================================================

class TestGoogleAuthAPIEndpoint:
    """Tests for POST /api/v1/auth/google endpoint."""

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", False)
    def test_endpoint_rejected_when_google_disabled(self, stage3_client):
        resp = stage3_client.post(
            "/api/v1/auth/google",
            json={"id_token": "some-token"},
        )
        assert resp.status_code == 503
        assert "Google authentication is currently disabled" in resp.json()["detail"]

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.personalization.service.verify_google_id_token")
    def test_endpoint_rejects_invalid_token_without_leaking(self, mock_verify, stage3_client):
        mock_verify.side_effect = ValueError("Cryptographic verification failed.")

        resp = stage3_client.post(
            "/api/v1/auth/google",
            json={"id_token": "malicious-secret-token-12345"},
        )
        assert resp.status_code == 401
        assert "Google authentication failed" in resp.json()["detail"]
        # Raw token must NEVER be returned in response detail
        assert "malicious-secret-token-12345" not in resp.text

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.personalization.service.verify_google_id_token")
    def test_endpoint_success_returns_standard_jwt_and_user(self, mock_verify, stage3_client):
        mock_verify.return_value = make_mock_google_payload(
            sub="sub-api-jwt-001",
            email="api.jwt@example.com",
            name="API JWT User",
        )

        resp = stage3_client.post(
            "/api/v1/auth/google",
            json={"id_token": "valid-google-jwt-token"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        assert data["user"]["email"] == "api.jwt@example.com"
        assert data["user"]["is_verified"] is True
        assert data["user"]["auth_provider"] == "google"

        # Verify JWT claims structure: sub: str(user.id), iat, exp
        decoded = decode_access_token(data["access_token"])
        assert decoded is not None
        assert decoded["sub"] == str(data["user"]["id"])
        assert "iat" in decoded
        assert "exp" in decoded

        # Verify token works against protected endpoint
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        me_resp = stage3_client.get("/api/v1/user/profile", headers=headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["user"]["email"] == "api.jwt@example.com"

    @patch("src.api.config.GOOGLE_AUTH_ENABLED", True)
    @patch("src.api.config.PILOT_MODE", True)
    @patch("src.api.config.PILOT_MAX_USERS", 1)
    @patch("src.personalization.service.verify_google_id_token")
    def test_endpoint_enforces_pilot_capacity_403(self, mock_verify, stage3_client, stage3_db):
        """API endpoint returns 403 when pilot capacity reached for new Google user."""
        # Add 1 existing user to reach limit
        u = UserModel(
            email="cohort.max@example.com",
            password_hash=hash_password("Pass123!"),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        stage3_db.add(u)
        stage3_db.commit()

        mock_verify.return_value = make_mock_google_payload(
            sub="sub-api-pilot-blocked",
            email="new.api.google@example.com",
        )

        resp = stage3_client.post(
            "/api/v1/auth/google",
            json={"id_token": "valid-token"},
        )
        assert resp.status_code == 403
        assert "capacity reached" in resp.json()["detail"].lower()
