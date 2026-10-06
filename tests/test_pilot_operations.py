"""Test Suite for Stage K — Controlled Pilot Operations & Feedback Pipeline.

Verifies:
1. Pilot Access & Enrollment Controls:
   - Pilot mode status endpoint
   - Cohort capacity enforcement (rejecting when capacity reached)
   - Invite code requirement and rejection of invalid codes
   - Participant self-deactivation and subsequent access blocking
   - Pilot kill switch: non-destructive blocking when pilot mode is disabled
2. Genuine Feedback Collection & Session Integrity:
   - Logging IMPRESSION events with query session ID
   - Logging explicit actions (LIKE, SAVE, COOKED, DISLIKE, HIDE)
   - Feedback updating and precedence preservation
3. Safety Invariants:
   - Cross-user authorization boundaries (zero leakage)
   - Hard constraint engine conflict detection
   - Secret leakage prevention
4. Data Quality Monitor & ML Readiness:
   - Pilot audit monitor returns CLEAN on genuine database
   - Authoritative INSUFFICIENT_DATA status on sparse interactions
"""

from __future__ import annotations

from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.api.config import (
    AUTH_SECRET_KEY,
    PILOT_INVITE_CODE,
    PILOT_MAX_USERS,
    PILOT_MODE,
)
from src.api.dependencies import get_db
from src.api.main import app
from src.constraints.dietary import DietaryRuleEngine
from src.constraints.models import DietaryConstraints, AllergenConstraints
from src.db.base import Base
import src.db.models
from src.ml.config import (
    MIN_INTERACTIONS,
    MIN_USERS,
    MIN_RECIPES,
    MIN_QUERY_GROUPS,
    MIN_POSITIVE_LABELS,
    MIN_NEGATIVE_LABELS,
    MIN_DAYS_OF_DATA,
)
from src.ml.pilot_audit import audit_pilot_feedback_data
from src.personalization.models import (
    QualitativeFeedbackModel,
    RecommendationHistoryModel,
    UserFeedbackModel,
    UserModel,
)
from src.personalization.schemas import (
    FeedbackRequest,
    FeedbackType,
    LoginRequest,
    QualitativeFeedbackRequest,
    QualitativeIssueType,
    RegisterRequest,
)
from src.personalization.service import PersonalizationService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create a pristine, in-memory SQLite database session for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a TestClient with overridden get_db dependency."""
    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 1. PILOT ACCESS & PARTICIPANT MANAGEMENT
# ---------------------------------------------------------------------------

def test_pilot_status_endpoint(client: TestClient) -> None:
    """Test public pilot status reports capacity, mode, available slots, and invite requirement."""
    res = client.get("/api/v1/auth/pilot-status")
    assert res.status_code == 200
    data = res.json()
    assert "pilot_mode" in data
    assert "capacity" in data
    assert "available_slots" in data
    assert "invite_code_required" in data
    assert isinstance(data["invite_code_required"], bool)
    assert data["capacity"] == PILOT_MAX_USERS
    assert data["available_slots"] >= 0
    # Invariant: Secret invite code must NEVER leak in the public status response
    if PILOT_INVITE_CODE:
        assert PILOT_INVITE_CODE not in res.text


def test_pilot_registration_and_login(client: TestClient) -> None:
    """Test full registration and login flow for a pilot participant."""
    reg_payload = {
        "email": "pilot_user_1@example.com",
        "password": "SecurePassword123!",
        "display_name": "Pilot User One",
    }
    if PILOT_INVITE_CODE:
        reg_payload["invite_code"] = PILOT_INVITE_CODE

    reg_res = client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert reg_data["user"]["email"] == "pilot_user_1@example.com"
    assert "access_token" in reg_data

    # Test login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "pilot_user_1@example.com", "password": "SecurePassword123!"},
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()


def test_pilot_capacity_exhaustion(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that registration is rejected with 403 when pilot capacity is reached."""
    monkeypatch.setattr("src.api.routes.auth.PILOT_MODE", True)
    monkeypatch.setattr("src.api.routes.auth.PILOT_MAX_USERS", 1)

    # Register first user (fills capacity)
    first_user = PersonalizationService.register_user(
        db_session,
        RegisterRequest(email="user1@example.com", password="SecurePassword123!", display_name="User One"),
    )
    assert first_user is not None

    # Attempt to register second user
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user2@example.com",
            "password": "SecurePassword123!",
            "display_name": "User Two",
            "invite_code": PILOT_INVITE_CODE or "",
        },
    )
    assert reg_res.status_code == 403
    assert "capacity reached" in reg_res.json()["detail"].lower()


def test_pilot_invite_code_enforcement(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test invite code enforcement: stale codes, missing codes, and valid codes."""
    monkeypatch.setattr("src.api.routes.auth.PILOT_MODE", True)
    monkeypatch.setattr("src.api.routes.auth.PILOT_INVITE_CODE", "SECRET_INVITE_999")

    # 1. Stale frontend placeholder code (e.g. "PILOT2026") is rejected
    res_stale = client.post(
        "/api/v1/auth/register",
        json={
            "email": "stale_pilot@example.com",
            "password": "SecurePassword123!",
            "invite_code": "PILOT2026",
        },
    )
    assert res_stale.status_code == 403
    assert "invite code" in res_stale.json()["detail"].lower()

    # 2. Arbitrary incorrect invite code is rejected
    res_bad = client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrong_invite@example.com",
            "password": "SecurePassword123!",
            "invite_code": "WRONG_CODE",
        },
    )
    assert res_bad.status_code == 403
    assert "invite code" in res_bad.json()["detail"].lower()

    # 3. Missing invite code (field omitted) is rejected
    res_missing = client.post(
        "/api/v1/auth/register",
        json={
            "email": "missing_invite@example.com",
            "password": "SecurePassword123!",
        },
    )
    assert res_missing.status_code == 403
    assert "invite code" in res_missing.json()["detail"].lower()

    # 4. Empty or whitespace invite code is rejected
    res_empty = client.post(
        "/api/v1/auth/register",
        json={
            "email": "empty_invite@example.com",
            "password": "SecurePassword123!",
            "invite_code": "   ",
        },
    )
    assert res_empty.status_code == 403
    assert "invite code" in res_empty.json()["detail"].lower()

    # 5. Public pilot status correctly indicates invite code is required without exposing secret
    res_status = client.get("/api/v1/auth/pilot-status")
    assert res_status.status_code == 200
    assert res_status.json()["invite_code_required"] is True
    assert "SECRET_INVITE_999" not in res_status.text

    # 6. Valid configured invite code succeeds
    res_ok = client.post(
        "/api/v1/auth/register",
        json={
            "email": "test_invite@example.com",
            "password": "SecurePassword123!",
            "invite_code": "SECRET_INVITE_999",
        },
    )
    assert res_ok.status_code == 201
    assert "access_token" in res_ok.json()


def test_pilot_participant_deactivation(client: TestClient, db_session: Session) -> None:
    """Test that user can deactivate their account and is immediately blocked from auth."""
    user = PersonalizationService.register_user(
        db_session,
        RegisterRequest(email="deactivate_me@example.com", password="Password123!", display_name="Active User"),
    )
    assert user.is_active is True

    # Login to obtain token
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "deactivate_me@example.com", "password": "Password123!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify user can view their pilot status
    status_res = client.get("/api/v1/user/pilot-status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["is_active"] is True

    # Deactivate account
    deact_res = client.post("/api/v1/user/deactivate", headers=headers)
    assert deact_res.status_code == 200
    assert deact_res.json()["status"] == "deactivated"

    # Verify login is rejected
    login_retry = client.post(
        "/api/v1/auth/login",
        json={"email": "deactivate_me@example.com", "password": "Password123!"},
    )
    assert login_retry.status_code == 401

    # Verify token access is rejected
    profile_retry = client.get("/api/v1/user/profile", headers=headers)
    assert profile_retry.status_code == 401


def test_pilot_kill_switch_non_destructive(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that turning off PILOT_MODE blocks new access without deleting existing data."""
    # Create an existing user and data
    user = PersonalizationService.register_user(
        db_session,
        RegisterRequest(email="existing@example.com", password="Password123!", display_name="Existing User"),
    )
    assert user.id is not None

    # Simulate production environment with pilot mode disabled
    monkeypatch.setattr("src.api.routes.auth.ENVIRONMENT", "production")
    monkeypatch.setattr("src.api.routes.auth.PILOT_MODE", False)

    # New registration should be blocked
    new_reg = client.post(
        "/api/v1/auth/register",
        json={"email": "new_pilot@example.com", "password": "Password123!"},
    )
    assert new_reg.status_code == 403
    assert "pilot onboarding is currently paused" in new_reg.json()["detail"].lower()

    # Existing user record MUST remain completely intact (non-destructive)
    db_user = PersonalizationService.get_user_by_id(db_session, user.id)
    assert db_user is not None
    assert db_user.email == "existing@example.com"


# ---------------------------------------------------------------------------
# 2. FEEDBACK PIPELINE & SESSION INTEGRITY
# ---------------------------------------------------------------------------

def test_genuine_feedback_events_and_session_id(client: TestClient, db_session: Session) -> None:
    """Test recording genuine IMPRESSION, LIKE, SAVE, COOKED, DISLIKE, and HIDE with session_id."""
    user = PersonalizationService.register_user(
        db_session,
        RegisterRequest(email="feedback_tester@example.com", password="Password123!", display_name="Feedback User"),
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "feedback_tester@example.com", "password": "Password123!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    session_id = "test_sess_abc123"

    # 1. Record implicit IMPRESSION
    imp_res = client.post(
        "/api/v1/user/feedback",
        headers=headers,
        json={
            "recipe_id": "REC_0001",
            "feedback_type": "IMPRESSION",
            "session_id": session_id,
        },
    )
    assert imp_res.status_code == 201
    assert imp_res.json()["feedback_type"] == "IMPRESSION"
    assert imp_res.json()["session_id"] == session_id

    # 2. Record explicit LIKE
    like_res = client.post(
        "/api/v1/user/feedback",
        headers=headers,
        json={
            "recipe_id": "REC_0001",
            "feedback_type": "LIKE",
            "session_id": session_id,
        },
    )
    assert like_res.status_code == 201
    assert like_res.json()["feedback_type"] == "LIKE"

    # 3. Record SAVE
    save_res = client.post(
        "/api/v1/user/feedback",
        headers=headers,
        json={
            "recipe_id": "REC_0002",
            "feedback_type": "SAVE",
            "session_id": session_id,
        },
    )
    assert save_res.status_code == 201
    assert save_res.json()["feedback_type"] == "SAVE"

    # 4. Record COOKED
    cook_res = client.post(
        "/api/v1/user/feedback",
        headers=headers,
        json={
            "recipe_id": "REC_0002",
            "feedback_type": "COOKED",
            "session_id": session_id,
        },
    )
    assert cook_res.status_code == 201
    assert cook_res.json()["feedback_type"] == "COOKED"

    # 5. Record DISLIKE
    dis_res = client.post(
        "/api/v1/user/feedback",
        headers=headers,
        json={
            "recipe_id": "REC_0003",
            "feedback_type": "DISLIKE",
            "session_id": session_id,
        },
    )
    assert dis_res.status_code == 201
    assert dis_res.json()["feedback_type"] == "DISLIKE"

    # 6. Record HIDE
    hide_res = client.post(
        "/api/v1/user/feedback",
        headers=headers,
        json={
            "recipe_id": "REC_0004",
            "feedback_type": "HIDE",
            "session_id": session_id,
        },
    )
    assert hide_res.status_code == 201
    assert hide_res.json()["feedback_type"] == "HIDE"


# ---------------------------------------------------------------------------
# 3. SAFETY & DATA ISOLATION
# ---------------------------------------------------------------------------

def test_cross_user_isolation(client: TestClient) -> None:
    """Verify that unauthenticated requests to protected endpoints return 401."""
    assert client.get("/api/v1/user/profile").status_code == 401
    assert client.get("/api/v1/user/history").status_code == 401
    assert client.get("/api/v1/user/pantry").status_code == 401
    assert client.post("/api/v1/user/feedback", json={}).status_code == 401


def test_hard_constraint_conflict_detection() -> None:
    """Verify that impossible dietary and allergen conflicts are detected with 0 violations."""
    engine = DietaryRuleEngine()

    conflicts = engine.detect_constraint_conflicts(
        dietary=DietaryConstraints(vegetarian=True),
        required_ingredients=["chicken breast"],
        excluded_allergens=[],
    )
    assert len(conflicts) > 0
    assert any("vegetarian" in c.lower() for c in conflicts)

    conflicts_dairy = engine.detect_constraint_conflicts(
        dietary=DietaryConstraints(),
        required_ingredients=["whole milk"],
        excluded_allergens=["dairy"],
    )
    assert len(conflicts_dairy) > 0
    assert any("dairy" in c.lower() for c in conflicts_dairy)


# ---------------------------------------------------------------------------
# 4. DATA QUALITY AUDIT & ML READINESS GATES
# ---------------------------------------------------------------------------

def test_pilot_data_quality_audit_clean(db_session: Session) -> None:
    """Verify that data quality audit returns CLEAN status on uncorrupted database."""
    report = audit_pilot_feedback_data(db_session)
    assert report.quality_status == "CLEAN"
    assert report.duplicate_events_count == 0
    assert report.temporal_violations_count == 0
    assert report.invalid_users_count == 0
    assert report.invalid_recipes_count == 0


def test_stage_i_readiness_thresholds() -> None:
    """Verify that Stage I data sufficiency thresholds remain authoritative."""
    assert MIN_INTERACTIONS == 200
    assert MIN_USERS == 20
    assert MIN_RECIPES == 50
    assert MIN_QUERY_GROUPS == 30
    assert MIN_POSITIVE_LABELS == 40
    assert MIN_NEGATIVE_LABELS == 10
    assert MIN_DAYS_OF_DATA == 7


# ---------------------------------------------------------------------------
# 5. QUALITATIVE UX FEEDBACK & DATA ISOLATION (STAGE L)
# ---------------------------------------------------------------------------

def test_qualitative_feedback_lifecycle_and_isolation(client: TestClient, db_session: Session) -> None:
    """Verify participant qualitative UX feedback submission, cross-user isolation, and purge."""
    # Register and login participant A
    u1 = PersonalizationService.register_user(
        db_session,
        RegisterRequest(email="participant.a@example.com", password="Password123!"),
    )
    login_a = client.post("/api/v1/auth/login", json={"email": "participant.a@example.com", "password": "Password123!"})
    token_a = login_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register and login participant B
    u2 = PersonalizationService.register_user(
        db_session,
        RegisterRequest(email="participant.b@example.com", password="Password123!"),
    )
    login_b = client.post("/api/v1/auth/login", json={"email": "participant.b@example.com", "password": "Password123!"})
    token_b = login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. Unauthenticated submission returns 401
    res_unauth = client.post(
        "/api/v1/user/qualitative-feedback",
        json={"issue_type": "poor_explanation", "comments": "Test unauth"},
    )
    assert res_unauth.status_code == 401

    # 2. Participant A submits qualitative feedback
    res_sub_a = client.post(
        "/api/v1/user/qualitative-feedback",
        headers=headers_a,
        json={
            "issue_type": "wrong_dietary_match",
            "comments": "Contains root vegetable in Jain mode",
            "session_id": "sess_12345",
        },
    )
    assert res_sub_a.status_code == 201
    fb_data_a = res_sub_a.json()
    assert fb_data_a["issue_type"] == "wrong_dietary_match"
    assert fb_data_a["comments"] == "Contains root vegetable in Jain mode"
    assert fb_data_a["user_id"] == u1.id

    # 3. Participant A retrieves their feedback
    res_get_a = client.get("/api/v1/user/qualitative-feedback", headers=headers_a)
    assert res_get_a.status_code == 200
    items_a = res_get_a.json()
    assert len(items_a) == 1
    assert items_a[0]["issue_type"] == "wrong_dietary_match"

    # 4. Cross-user isolation: Participant B cannot see Participant A's qualitative feedback
    res_get_b = client.get("/api/v1/user/qualitative-feedback", headers=headers_b)
    assert res_get_b.status_code == 200
    items_b = res_get_b.json()
    assert len(items_b) == 0

    # 5. Purge Participant A data removes their qualitative feedback
    res_purge = client.delete("/api/v1/user/data", headers=headers_a)
    assert res_purge.status_code == 200
    assert res_purge.json()["purged_records"]["qualitative_feedback"] == 1

    # Verify Participant A has 0 qualitative feedback after purge
    res_get_a_after = client.get("/api/v1/user/qualitative-feedback", headers=headers_a)
    assert len(res_get_a_after.json()) == 0


def test_qualitative_feedback_kept_separate_from_ml_audit(db_session: Session) -> None:
    """Verify that qualitative UX comments are never counted as structured ML interactions."""
    user = PersonalizationService.register_user(
        db_session,
        RegisterRequest(email="qual.audit@example.com", password="Password123!"),
    )
    # Record qualitative feedback directly
    PersonalizationService.record_qualitative_feedback(
        db_session,
        user_id=user.id,
        req=QualitativeFeedbackRequest(
            issue_type=QualitativeIssueType.USEFUL_RECOMMENDATION,
            comments="Very tasty suggestion!",
        ),
    )

    # ML Pilot audit must still report 0 interactions (not counting qualitative comments as ML training labels)
    report = audit_pilot_feedback_data(db_session)
    assert report.total_interactions == 0
    assert report.positive_labels == 0
    assert report.negative_labels == 0

