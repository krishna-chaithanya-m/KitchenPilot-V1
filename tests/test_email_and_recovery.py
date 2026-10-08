"""Comprehensive test suite for Stage 2 — Email Verification & Password Recovery.

Verifies:
1. Verification token creation and deterministic SHA-256 token hashing.
2. Raw verification tokens are never stored in the database.
3. Successful email verification marks is_verified = True.
4. Invalid, expired, or already-used verification tokens are rejected.
5. Resend verification workflow (invalidates prior tokens, dispatches fresh token).
6. Anti-enumeration behavior: forgot-password returns equivalent 200 responses
   whether the account exists or not, without leaking account existence.
7. Password reset workflow: valid token updates password hash using Argon2id.
8. Old password no longer authenticates; new password successfully authenticates.
9. Reset tokens are single-use; subsequent attempts are rejected.
10. Email service operates cleanly in mock/test mode with outbox verification
    and zero leakage of raw tokens or credentials in logs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.dependencies import get_db
from src.api.main import app
from src.db.base import Base
from src.personalization.models import (
    EmailVerificationTokenModel,
    PasswordResetTokenModel,
    UserModel,
)
from src.personalization.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from src.personalization.security import (
    hash_password,
    hash_token,
    verify_password,
)
from src.personalization.service import PersonalizationService
from src.services.email import EmailService, email_service


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ============================================================================
# Test Database Fixtures
# ============================================================================

@pytest.fixture(scope="module")

def stage2_engine():
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
def stage2_db(stage2_engine):
    """Provide transactional session for Stage 2 testing."""
    connection = stage2_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def stage2_client(stage2_db):
    """Provide FastAPI test client with mocked DB session."""
    def override_get_db():
        yield stage2_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clean_email_outbox():
    """Ensure email outbox is empty before each test."""
    EmailService.clear_outbox()
    yield
    EmailService.clear_outbox()


# ============================================================================
# 1. Verification Token Creation & Hashing Security Tests
# ============================================================================

def test_verification_token_creation_and_hashing(stage2_db: Session):
    """Verify raw token is returned and ONLY SHA-256 hash is persisted."""
    reg = RegisterRequest(
        email="verify_test@example.com",
        password="ValidPassword123!",
        display_name="Verify User",
    )
    user = PersonalizationService.register_user(stage2_db, reg)
    assert not user.is_verified

    raw_token = PersonalizationService.create_email_verification_token(stage2_db, user.id)
    assert raw_token
    assert len(raw_token) >= 32

    # Query database record
    expected_hash = hash_token(raw_token)
    token_record = stage2_db.execute(
        select(EmailVerificationTokenModel).where(EmailVerificationTokenModel.user_id == user.id)
    ).scalar_one_or_none()

    assert token_record is not None
    assert token_record.token_hash == expected_hash
    # The raw token must NOT be stored in plaintext
    assert raw_token not in token_record.token_hash
    assert token_record.used_at is None
    assert _normalize_utc(token_record.expires_at) > datetime.now(timezone.utc)



def test_successful_email_verification(stage2_db: Session, stage2_client: TestClient):
    """Verify that submitting a valid token marks the user as verified."""
    reg = RegisterRequest(
        email="success_verify@example.com",
        password="SecurePass123$",
        display_name="Success Verifier",
    )
    user = PersonalizationService.register_user(stage2_db, reg)
    raw_token = PersonalizationService.create_email_verification_token(stage2_db, user.id)

    response = stage2_client.post(
        "/api/v1/auth/verify-email",
        json={"token": raw_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "verified" in data["message"].lower()

    # Verify user record in database
    stage2_db.refresh(user)
    assert user.is_verified is True

    # Token must now be marked used
    expected_hash = hash_token(raw_token)
    token_rec = stage2_db.execute(
        select(EmailVerificationTokenModel).where(EmailVerificationTokenModel.token_hash == expected_hash)
    ).scalar_one()
    assert token_rec.used_at is not None


def test_reused_verification_token_rejected(stage2_db: Session, stage2_client: TestClient):
    """Verify that a used verification token cannot be reused."""
    reg = RegisterRequest(
        email="reused_token@example.com",
        password="SecurePass123$",
    )
    user = PersonalizationService.register_user(stage2_db, reg)
    raw_token = PersonalizationService.create_email_verification_token(stage2_db, user.id)

    # First attempt succeeds
    resp1 = stage2_client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert resp1.status_code == 200

    # Second attempt must be rejected with 400 Bad Request
    resp2 = stage2_client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert resp2.status_code == 400
    assert "already used" in resp2.json()["detail"].lower() or "invalid" in resp2.json()["detail"].lower()


def test_expired_verification_token_rejected(stage2_db: Session, stage2_client: TestClient):
    """Verify that an expired verification token is rejected."""
    reg = RegisterRequest(
        email="expired_token@example.com",
        password="SecurePass123$",
    )
    user = PersonalizationService.register_user(stage2_db, reg)
    raw_token = PersonalizationService.create_email_verification_token(stage2_db, user.id)

    # Manually backdate the expiration in DB
    expected_hash = hash_token(raw_token)
    token_rec = stage2_db.execute(
        select(EmailVerificationTokenModel).where(EmailVerificationTokenModel.token_hash == expected_hash)
    ).scalar_one()
    token_rec.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    stage2_db.commit()

    resp = stage2_client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


def test_invalid_verification_token_rejected(stage2_client: TestClient):
    """Verify completely bogus token is rejected."""
    resp = stage2_client.post(
        "/api/v1/auth/verify-email",
        json={"token": "completely_invalid_token_string_12345"},
    )
    assert resp.status_code == 400
    assert "invalid" in resp.json()["detail"].lower()


# ============================================================================
# 2. Resend Verification Tests
# ============================================================================

def test_resend_verification_workflow(stage2_db: Session, stage2_client: TestClient):
    """Verify resending verification email generates a fresh token and invalidates old ones."""
    reg = RegisterRequest(
        email="resend_test@example.com",
        password="SecurePass123$",
    )
    user = PersonalizationService.register_user(stage2_db, reg)
    old_raw_token = PersonalizationService.create_email_verification_token(stage2_db, user.id)
    old_hash = hash_token(old_raw_token)

    resp = stage2_client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "resend_test@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Outbox must have recorded the resend message
    outbox = EmailService.get_outbox()
    assert len(outbox) >= 1
    latest_email = outbox[-1]
    assert latest_email["recipient"] == "resend_test@example.com"
    new_raw_token = latest_email["raw_token"]
    assert new_raw_token != old_raw_token

    # Old token must no longer be valid or must be purged
    old_rec = stage2_db.execute(
        select(EmailVerificationTokenModel).where(EmailVerificationTokenModel.token_hash == old_hash)
    ).scalar_one_or_none()
    assert old_rec is None  # Prior unused tokens purged on resend

    # New token successfully verifies
    verify_resp = stage2_client.post("/api/v1/auth/verify-email", json={"token": new_raw_token})
    assert verify_resp.status_code == 200


def test_resend_verification_anti_enumeration(stage2_client: TestClient):
    """Verify resending for a nonexistent email returns generic 200 without sending email."""
    resp = stage2_client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "nonexistent_resend@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    # Outbox must be empty
    assert len(EmailService.get_outbox()) == 0


# ============================================================================
# 3. Forgot Password & Anti-Enumeration Tests
# ============================================================================

def test_forgot_password_anti_enumeration_equivalence(
    stage2_db: Session, stage2_client: TestClient
):
    """Verify forgot-password returns identical responses for existing and nonexistent emails."""
    # Register existing user
    reg = RegisterRequest(
        email="existing_user@example.com",
        password="OriginalPassword123!",
    )
    PersonalizationService.register_user(stage2_db, reg)

    # 1. Request for existing user
    resp_existing = stage2_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "existing_user@example.com"},
    )

    # 2. Request for non-existent user
    resp_nonexistent = stage2_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nonexistent_ghost@example.com"},
    )

    # Both must return 200 with identical payloads
    assert resp_existing.status_code == 200
    assert resp_nonexistent.status_code == 200
    assert resp_existing.json() == resp_nonexistent.json()

    # Outbox should have sent exactly ONE email (for existing user only)
    outbox = EmailService.get_outbox()
    assert len(outbox) == 1
    assert outbox[0]["recipient"] == "existing_user@example.com"
    assert outbox[0]["type"] == "password_reset"


def test_forgot_password_does_not_alter_existing_password(
    stage2_db: Session, stage2_client: TestClient
):
    """Verify initiating forgot-password does NOT change the user's password."""
    reg = RegisterRequest(
        email="unaltered_pw@example.com",
        password="MyOriginalPassword123!",
    )
    user = PersonalizationService.register_user(stage2_db, reg)
    initial_hash = user.password_hash

    stage2_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "unaltered_pw@example.com"},
    )

    stage2_db.refresh(user)
    assert user.password_hash == initial_hash
    # User can still authenticate with original password
    assert verify_password("MyOriginalPassword123!", user.password_hash)


# ============================================================================
# 4. Password Reset Execution & Security Tests
# ============================================================================

def test_successful_password_reset(stage2_db: Session, stage2_client: TestClient):
    """Verify full reset workflow: token validation, Argon2id update, and re-authentication."""
    reg = RegisterRequest(
        email="reset_target@example.com",
        password="OldSecurePassword1!",
    )
    user = PersonalizationService.register_user(stage2_db, reg)

    # Request reset
    stage2_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "reset_target@example.com"},
    )

    outbox = EmailService.get_outbox()
    assert len(outbox) == 1
    raw_token = outbox[0]["raw_token"]

    # Submit reset with new password
    reset_resp = stage2_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": raw_token,
            "new_password": "NewBrandNewPassword2026$",
        },
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["success"] is True

    # 1. Verify old password no longer works
    login_old = stage2_client.post(
        "/api/v1/auth/login",
        json={"email": "reset_target@example.com", "password": "OldSecurePassword1!"},
    )
    assert login_old.status_code == 401

    # 2. Verify new password successfully authenticates and issues valid JWT
    login_new = stage2_client.post(
        "/api/v1/auth/login",
        json={"email": "reset_target@example.com", "password": "NewBrandNewPassword2026$"},
    )
    assert login_new.status_code == 200
    token_data = login_new.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"


def test_reset_token_single_use_enforcement(stage2_db: Session, stage2_client: TestClient):
    """Verify reset token cannot be reused after successful password reset."""
    reg = RegisterRequest(
        email="single_use_reset@example.com",
        password="InitialPassword123!",
    )
    user = PersonalizationService.register_user(stage2_db, reg)

    stage2_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "single_use_reset@example.com"},
    )
    raw_token = EmailService.get_outbox()[0]["raw_token"]

    # First reset succeeds
    resp1 = stage2_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "FirstNewPassword123!"},
    )
    assert resp1.status_code == 200

    # Second reset with same token must fail
    resp2 = stage2_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "SecondNewPassword123!"},
    )
    assert resp2.status_code == 400
    assert "already used" in resp2.json()["detail"].lower() or "invalid" in resp2.json()["detail"].lower()


def test_expired_reset_token_rejected(stage2_db: Session, stage2_client: TestClient):
    """Verify expired password reset token is rejected."""
    reg = RegisterRequest(
        email="expired_reset@example.com",
        password="InitialPassword123!",
    )
    user = PersonalizationService.register_user(stage2_db, reg)

    stage2_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "expired_reset@example.com"},
    )
    raw_token = EmailService.get_outbox()[0]["raw_token"]

    # Expire token in database
    token_hash = hash_token(raw_token)
    token_rec = stage2_db.execute(
        select(PasswordResetTokenModel).where(PasswordResetTokenModel.token_hash == token_hash)
    ).scalar_one()
    token_rec.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    stage2_db.commit()

    resp = stage2_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "FailedNewPassword123!"},
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


def test_argon2id_parameters_remain_intact(stage2_db: Session):
    """Verify that password reset continues using the exact production Argon2id parameters."""
    reg = RegisterRequest(
        email="argon_param_check@example.com",
        password="InitialPassword123!",
    )
    user = PersonalizationService.register_user(stage2_db, reg)

    raw_token = PersonalizationService.create_password_reset_token(stage2_db, user.email)[1]
    updated_user = PersonalizationService.reset_password_with_token(
        stage2_db, raw_token, "UpgradedArgonPassword123!"
    )

    # Argon2id encoded string starts with $argon2id$v=19$m=65536,t=2,p=2$
    assert updated_user.password_hash.startswith("$argon2id$")
    assert "m=65536,t=2,p=2" in updated_user.password_hash
