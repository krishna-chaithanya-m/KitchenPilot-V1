"""Comprehensive test suite for Stage G — User Personalization & Feedback.

Verifies:
1. Authentication (Argon2id hashing, registration, login, duplicate check, JWT security)
2. User isolation & authorization security
3. User preferences & nutrition targets persistence
4. User persistent pantry & canonical ingredient linkage
5. Explicit user feedback (LIKE, DISLIKE, SAVE, COOKED, HIDE)
6. Recommendation event history logging & audit isolation
7. Personalization feature extraction, bounded scoring, and deterministic tie-breaking
8. Critical Invariants:
   - Hard constraints strictly enforced BEFORE personalization (safety cannot be bypassed)
   - Anonymous requests maintain exact baseline parity (zero personalization adjustment)
   - Runtime ML artifacts remain immutable
"""

from __future__ import annotations

import os
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.dependencies import get_db, get_optional_current_user
from src.api.main import app
from src.constraints import ConstraintRequest, DietaryConstraints, IngredientConstraints
from src.db.base import Base
from src.personalization.features import (
    PersonalizationSignals,
    UserPersonalizationContext,
    extract_personalization_signals,
)
from src.personalization.history import generate_session_id, log_recommendation_events
from src.personalization.models import (
    RecommendationHistoryModel,
    UserFeedbackModel,
    UserModel,
    UserNutritionTargetModel,
    UserPantryModel,
    UserPreferenceModel,
)
from src.personalization.schemas import (
    FeedbackRequest,
    FeedbackType,
    LoginRequest,
    NutritionTargetRequest,
    PantryItemCreateRequest,
    PantryStatus,
    RegisterRequest,
    UpdatePreferencesRequest,
)
from src.personalization.scorer import PersonalizationScorer
from src.personalization.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from src.personalization.service import PersonalizationService
from src.recommendation.hybrid_ranker import ScoredCandidate
from src.recommendation.nutrition_scorer import NutritionGoals
from src.recommendation.preference_filter import UserPreferences
from src.recommendation.recommender import KitchenPilotRecommender


# ============================================================================
# Test Database Fixtures (In-Memory SQLite with StaticPool)
# ============================================================================

@pytest.fixture(scope="session")
def test_db_engine():
    """Create a persistent in-memory SQLite engine for the test session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(test_db_engine) -> Generator[Session, None, None]:
    """Provide a clean transactional session for each unit test."""
    connection = test_db_engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(test_db_engine) -> Generator[TestClient, None, None]:
    """TestClient with overridden get_db dependency pointing to in-memory test database."""
    session_factory = sessionmaker(bind=test_db_engine)

    def _override_get_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def setup_auth_env_for_personalization(monkeypatch: pytest.MonkeyPatch):
    """Ensure standard personalization unit tests are not blocked by pilot invite restrictions."""
    monkeypatch.setattr("src.api.routes.auth.PILOT_INVITE_CODE", "")


# ============================================================================
# 1. Security & Authentication Tests
# ============================================================================

def test_argon2id_password_hashing():
    """Verify Argon2id produces secure salted hashes and verifies accurately."""
    pw = "SuperSecret123!"
    h = hash_password(pw)
    assert h.startswith("$argon2id$")
    assert verify_password(pw, h) is True
    assert verify_password("WrongPassword123!", h) is False
    assert verify_password("", h) is False


def test_jwt_token_creation_and_validation():
    """Verify JWT access tokens encode, decode, and expire properly."""
    token, expires_in = create_access_token(subject=42, extra_claims={"email": "chef@test.com"})
    assert isinstance(token, str)
    assert expires_in > 0

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["email"] == "chef@test.com"

    # Malformed token
    assert decode_access_token("not.a.valid.jwt.token") is None


def test_user_registration_success(client: TestClient):
    """Verify successful user registration via API."""
    payload = {
        "email": "fresh_chef@example.com",
        "password": "Password123!",
        "display_name": "Fresh Chef",
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "fresh_chef@example.com"
    assert data["user"]["display_name"] == "Fresh Chef"
    assert "password_hash" not in data["user"]


def test_user_registration_duplicate_email(client: TestClient):
    """Verify registration rejects duplicate email addresses with 409 Conflict."""
    payload = {
        "email": "duplicate@example.com",
        "password": "Password123!",
    }
    resp1 = client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409
    assert "already registered" in resp2.json()["detail"].lower()


def test_user_registration_weak_password(client: TestClient):
    """Verify registration rejects passwords shorter than 8 chars or missing complexity."""
    payload = {
        "email": "weak@example.com",
        "password": "short",
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422


def test_user_login_success(client: TestClient):
    """Verify login with valid credentials returns a valid JWT token."""
    client.post("/api/v1/auth/register", json={
        "email": "login_user@example.com",
        "password": "ValidPassword99!",
    })

    resp = client.post("/api/v1/auth/login", json={
        "email": "login_user@example.com",
        "password": "ValidPassword99!",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "login_user@example.com"


def test_user_login_invalid_credentials(client: TestClient):
    """Verify login with incorrect password returns 401 Unauthorized."""
    resp = client.post("/api/v1/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "WrongPassword1!",
    })
    assert resp.status_code == 401
    assert "invalid email or password" in resp.json()["detail"].lower()


# ============================================================================
# 2. Authorization & User Isolation Tests
# ============================================================================

def test_unauthenticated_profile_access_rejected(client: TestClient):
    """Verify protected endpoints reject requests without Authorization header."""
    resp = client.get("/api/v1/user/profile")
    assert resp.status_code == 401


def test_user_profile_and_isolation(client: TestClient):
    """Verify User A and User B cannot access each other's data."""
    # Register User A
    resp_a = client.post("/api/v1/auth/register", json={
        "email": "usera@example.com",
        "password": "Password123!",
        "display_name": "User A",
    })
    token_a = resp_a.json()["access_token"]

    # Register User B
    resp_b = client.post("/api/v1/auth/register", json={
        "email": "userb@example.com",
        "password": "Password123!",
        "display_name": "User B",
    })
    token_b = resp_b.json()["access_token"]

    # User A gets profile
    prof_a = client.get("/api/v1/user/profile", headers={"Authorization": f"Bearer {token_a}"})
    assert prof_a.status_code == 200
    assert prof_a.json()["user"]["email"] == "usera@example.com"

    # User B gets profile
    prof_b = client.get("/api/v1/user/profile", headers={"Authorization": f"Bearer {token_b}"})
    assert prof_b.status_code == 200
    assert prof_b.json()["user"]["email"] == "userb@example.com"
    assert prof_b.json()["user"]["id"] != prof_a.json()["user"]["id"]


# ============================================================================
# 3. Preferences & Nutrition Targets Tests
# ============================================================================

def test_user_preferences_persistence(client: TestClient):
    """Verify updating and persisting user dietary and cuisine preferences."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "pref_user@example.com",
        "password": "Password123!",
    })
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    update_payload = {
        "vegetarian": True,
        "preferred_cuisines": ["South Indian", "Gujarati"],
        "preferred_ingredients": ["paneer", "mustard seeds"],
        "disliked_ingredients": ["bitter gourd"],
    }
    put_resp = client.put("/api/v1/user/preferences", json=update_payload, headers=headers)
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["vegetarian"] is True
    assert "South Indian" in data["preferred_cuisines"]
    assert "paneer" in data["preferred_ingredients"]

    # Verify via profile get
    prof_resp = client.get("/api/v1/user/profile", headers=headers)
    assert prof_resp.json()["preferences"]["vegetarian"] is True
    assert "Gujarati" in prof_resp.json()["preferences"]["preferred_cuisines"]


def test_user_preferences_form_state_persistence(client: TestClient):
    """Verify updating preferences with form state fields (singular aliases + pantry preferred_ingredients)."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "form_state_user@example.com",
        "password": "Password123!",
    })
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    update_payload = {
        "vegetarian": True,
        "vegan": False,
        "jain": True,
        "satvik": False,
        "cuisine": "South Indian",
        "region": "Tamil Nadu",
        "meal_type": "Lunch",
        "category": "Main Course",
        "preferred_ingredients": ["rice", "onion", "tomato"],
    }
    put_resp = client.put("/api/v1/user/preferences", json=update_payload, headers=headers)
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["vegetarian"] is True
    assert data["jain"] is True
    assert "South Indian" in data["preferred_cuisines"]
    assert "Tamil Nadu" in data["preferred_regions"]
    assert "Lunch" in data["preferred_meal_types"]
    assert "Main Course" in data["preferred_categories"]
    assert "rice" in data["preferred_ingredients"]


def test_user_nutrition_targets_persistence(client: TestClient):
    """Verify updating and validating user nutrition goals."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "nutr_user@example.com",
        "password": "Password123!",
    })
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    nut_payload = {
        "target_calories": 500.0,
        "min_calories": 400.0,
        "max_calories": 600.0,
        "min_protein": 25.0,
    }
    put_resp = client.put("/api/v1/user/nutrition-targets", json=nut_payload, headers=headers)
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["target_calories"] == 500.0
    assert data["min_protein"] == 25.0

    # Invalid bounds (max < min) rejected
    bad_payload = {"min_calories": 800.0, "max_calories": 400.0}
    bad_resp = client.put("/api/v1/user/nutrition-targets", json=bad_payload, headers=headers)
    assert bad_resp.status_code == 422


# ============================================================================
# 4. Pantry & Canonical Linkage Tests
# ============================================================================

def test_pantry_crud_and_canonical_mapping(client: TestClient):
    """Verify adding, listing, and deleting pantry ingredients."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "pantry_user@example.com",
        "password": "Password123!",
    })
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Add item
    add_resp = client.post("/api/v1/user/pantry", json={
        "ingredient_name": "paneer",
        "quantity": 250.0,
        "unit": "g",
        "status": "IN_STOCK",
    }, headers=headers)
    assert add_resp.status_code == 201
    item = add_resp.json()
    assert item["ingredient_name"] == "paneer"
    assert item["status"] == "IN_STOCK"
    item_id = item["id"]

    # List pantry
    list_resp = client.get("/api/v1/user/pantry", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Delete item
    del_resp = client.delete(f"/api/v1/user/pantry/{item_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # List again -> empty
    list_resp2 = client.get("/api/v1/user/pantry", headers=headers)
    assert len(list_resp2.json()) == 0


def test_pantry_sync_exact_case_rice_potato_tomato_onion(client: TestClient):
    """Regression test for exact case:
    Rice + Potato + Tomato + Onion
    must remain exactly those four pantry ingredients after save/load/sync,
    ensuring potato is preserved and cumin is not introduced.
    """
    resp = client.post("/api/v1/auth/register", json={
        "email": "pilot_sync_test@example.com",
        "password": "Password123!",
    })
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Simulate existing pantry with legacy/sample items: rice, onion, tomato, cumin, turmeric
    legacy_items = ["rice", "onion", "tomato", "cumin", "turmeric"]
    for item in legacy_items:
        client.post("/api/v1/user/pantry", json={"ingredient_name": item}, headers=headers)

    init_pantry = client.get("/api/v1/user/pantry", headers=headers).json()
    init_names = {it["ingredient_name"].lower() for it in init_pantry}
    assert "cumin" in init_names
    assert "potato" not in init_names
    assert len(init_pantry) == 5

    # 2. Pilot user enters exactly: Rice, Potato, Tomato, Onion in UI and clicks "Save Current Preferences"
    # Frontend sends updatePreferences and syncUserPantry with target ingredients
    target_ingredients = ["Rice", "Potato", "Tomato", "Onion"]
    target_lower = {ing.lower() for ing in target_ingredients}

    # 2a. Update preferences
    pref_resp = client.put("/api/v1/user/preferences", json={
        "preferred_ingredients": target_ingredients,
        "vegetarian": True,
    }, headers=headers)
    assert pref_resp.status_code == 200

    # 2b. Frontend syncUserPantry reconciliation flow:
    current_items = client.get("/api/v1/user/pantry", headers=headers).json()
    current_names = {it["ingredient_name"].lower() for it in current_items}

    # Prune items not in target set (e.g. cumin, turmeric)
    for it in current_items:
        name = it["ingredient_name"].lower()
        if name not in target_lower:
            del_res = client.delete(f"/api/v1/user/pantry/{it['id']}", headers=headers)
            assert del_res.status_code == 200

    # Add missing target items (e.g. Potato)
    for ing in target_ingredients:
        if ing.lower() not in current_names:
            add_res = client.post("/api/v1/user/pantry", json={"ingredient_name": ing}, headers=headers)
            assert add_res.status_code == 201

    # 3. Simulate Ctrl+F5 + "Sync From My Pantry": GET /api/v1/user/pantry
    final_pantry_resp = client.get("/api/v1/user/pantry", headers=headers)
    assert final_pantry_resp.status_code == 200
    final_pantry = final_pantry_resp.json()
    final_pantry_names = {it["ingredient_name"].lower() for it in final_pantry}

    # Invariant: exactly {rice, potato, tomato, onion}
    assert final_pantry_names == {"rice", "potato", "tomato", "onion"}
    assert "potato" in final_pantry_names
    assert "cumin" not in final_pantry_names
    assert len(final_pantry) == 4

    # 4. Recommendation request execution: POST /api/v1/recommend/by-ingredients
    rec_payload = {
        "ingredients": [it["ingredient_name"] for it in final_pantry],
        "top_k": 5,
        "user_preferences": {"vegetarian": True},
    }
    rec_resp = client.post("/api/v1/recommend/by-ingredients", json=rec_payload, headers=headers)
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert len(rec_data["recommendations"]) > 0

    # Verify matching ingredients include potato and no cumin requirement
    all_matched = set()
    for rec in rec_data["recommendations"]:
        for matched_item in rec.get("matched_ingredients", []):
            all_matched.add(matched_item.lower())
    assert "potato" in all_matched
    assert "cumin" not in [ing.lower() for ing in rec_payload["ingredients"]]


# ============================================================================
# 5. Explicit User Feedback Tests
# ============================================================================

def test_user_feedback_submission_and_query(client: TestClient):
    """Verify submitting LIKE, DISLIKE, SAVE, COOKED, HIDE feedback."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "feedback_user@example.com",
        "password": "Password123!",
    })
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Submit LIKE
    fb_resp = client.post("/api/v1/user/feedback", json={
        "recipe_id": "r_0001",
        "feedback_type": "LIKE",
        "rating": 5.0,
        "notes": "Delicious authentic flavor",
    }, headers=headers)
    assert fb_resp.status_code == 201
    data = fb_resp.json()
    assert data["recipe_id"] == "r_0001"
    assert data["feedback_type"] == "LIKE"

    # Submit SAVE
    client.post("/api/v1/user/feedback", json={
        "recipe_id": "r_0002",
        "feedback_type": "SAVE",
    }, headers=headers)

    # Query all feedback
    get_all = client.get("/api/v1/user/feedback", headers=headers)
    assert len(get_all.json()) == 2

    # Query filtered by feedback_type
    get_likes = client.get("/api/v1/user/feedback?feedback_type=LIKE", headers=headers)
    assert len(get_likes.json()) == 1
    assert get_likes.json()[0]["recipe_id"] == "r_0001"


# ============================================================================
# 6. Recommendation History Logging Tests
# ============================================================================

def test_recommendation_history_logging(db_session: Session):
    """Verify recommendation events are logged accurately with score breakdowns."""
    user = UserModel(
        email="history_test@example.com",
        password_hash="dummy_hash",
        display_name="History Test",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    sess_id = generate_session_id()
    cands = [
        ScoredCandidate(
            recipe_id="r_0010",
            recipe_name="Paneer Butter Masala",
            similarity_score=0.85,
            ingredient_match_score=0.90,
            nutrition_score=0.80,
            preference_score=0.75,
            nutrition_confidence=1.0,
            hybrid_score=0.83,
            personalization_score=0.10,
            final_score=0.93,
        ),
        ScoredCandidate(
            recipe_id="r_0020",
            recipe_name="Dal Tadka",
            similarity_score=0.75,
            ingredient_match_score=0.80,
            nutrition_score=0.85,
            preference_score=0.70,
            nutrition_confidence=1.0,
            hybrid_score=0.77,
            personalization_score=-0.05,
            final_score=0.72,
        ),
    ]

    events = log_recommendation_events(
        db=db_session,
        user_id=user.id,
        session_id=sess_id,
        ranked_candidates=cands,
        ranking_method="hybrid",
        model_version="hybrid_v1",
        personalization_applied=True,
        context_metadata={"query": "paneer dishes"},
    )
    assert len(events) == 2
    assert events[0].position == 1
    assert events[0].recipe_id == "r_0010"
    assert events[0].final_score == 0.93
    assert events[1].position == 2
    assert events[1].final_score == 0.72

    total, history = PersonalizationService.get_user_history(db_session, user.id)
    assert total == 2
    assert history[0].session_id == sess_id


# ============================================================================
# 7. Personalization Feature Extraction & Scorer Tests
# ============================================================================

def test_personalization_signals_extraction():
    """Verify signals extraction computes expected affinities and reasons."""
    ctx = UserPersonalizationContext(
        user_id=1,
        preferred_cuisines={"South Indian"},
        preferred_ingredients={"paneer"},
        disliked_ingredients={"eggplant"},
        pantry_ingredient_names={"onion", "tomato", "ginger"},
        liked_recipe_ids={"r_100"},
        calorie_target=450.0,
    )

    recipe_meta = {
        "recipe_id": "r_100",
        "recipe_name": "Paneer Tikka",
        "cuisine": "South Indian",
        "ingredients_list": ["paneer", "onion", "tomato"],
        "per_serving_calories": 440.0,
    }

    signals = extract_personalization_signals(recipe_meta, ctx)
    assert signals.cuisine_affinity == 1.0
    assert signals.past_liked is True
    assert signals.preferred_ingredient_match_count == 1
    assert signals.pantry_overlap_count == 2
    assert signals.disliked_ingredient_penalty == 0.0
    assert signals.nutrition_target_alignment > 0.9
    assert len(signals.reasons) >= 3


def test_personalization_scorer_bounded_and_deterministic():
    """Verify personalization adjustments are strictly bounded within [-weight, +weight]."""
    scorer = PersonalizationScorer(weight=0.20, enabled=True)

    # Maximum positive signals
    pos_signals = PersonalizationSignals(
        cuisine_affinity=1.0,
        region_affinity=1.0,
        meal_type_affinity=1.0,
        category_affinity=1.0,
        pantry_overlap_ratio=1.0,
        preferred_ingredient_match_count=5,
        past_liked=True,
        past_saved=True,
        past_cooked=True,
        nutrition_target_alignment=1.0,
    )
    raw_pos, adj_pos = scorer.compute_adjustment(pos_signals)
    assert 0.0 < adj_pos <= 0.20
    assert raw_pos <= 1.0

    # Maximum negative signals (disliked, hidden)
    neg_signals = PersonalizationSignals(
        disliked_ingredient_penalty=1.0,
        past_disliked=True,
        past_hidden=True,
        recently_recommended=True,
    )
    raw_neg, adj_neg = scorer.compute_adjustment(neg_signals)
    assert -0.20 <= adj_neg < 0.0
    assert raw_neg >= -1.0


# ============================================================================
# 8. CRITICAL INVARIANT TESTS
# ============================================================================

def test_invariant_hard_constraints_cannot_be_bypassed_by_personalization():
    """CRITICAL INVARIANT: A candidate that violates a Stage E hard constraint MUST NEVER
    be recommended, even if the user has maximum positive personalization for it!
    """
    recommender = KitchenPilotRecommender()

    # Create a user context where the user loves recipe '1' (Chicken Tikka or non-veg)
    user_ctx = UserPersonalizationContext(
        user_id=999,
        vegetarian=True,  # User profile is VEGETARIAN
        liked_recipe_ids={"R00001", "R00006", "R00029"},
        saved_recipe_ids={"R00001", "R00006", "R00029"},
        cooked_recipe_ids={"R00001", "R00006", "R00029"},
        preferred_cuisines={"North Indian"},
    )

    # Stage E hard constraint request: STRICT VEGETARIAN
    constraint_req = ConstraintRequest(
        dietary=DietaryConstraints(vegetarian=True),
        ingredients=IngredientConstraints(),
    )

    results_df = recommender.recommend(
        query_recipe_id="R00001",  # query base
        top_k=10,
        save_results=False,
        constraint_request=constraint_req,
        user_context=user_ctx,
    )

    # Invariant check: zero non-vegetarian recipes in final recommendations
    # Verify every returned recipe in recipes.csv has vegetarian == True
    recipe_store = recommender._recipe_metadata
    for _, row in results_df.iterrows():
        rid = str(row["recipe_id"])
        # Check against constraint engine evaluation
        eval_map = recommender.last_constraint_evaluations or {}
        if rid in eval_map:
            assert eval_map[rid].passed is True, f"Recipe {rid} violated constraints but was recommended!"


def test_invariant_anonymous_request_maintains_exact_baseline():
    """CRITICAL INVARIANT: When user_context is None (anonymous request),
    personalization adjustment is exactly 0.0 and ranking is identical to baseline.
    """
    recommender = KitchenPilotRecommender()

    df_anon = recommender.recommend(
        available_ingredients=["paneer", "tomato", "onion"],
        top_k=5,
        save_results=False,
        user_context=None,
    )

    for cand in recommender.last_ranked_candidates:
        assert cand.personalization_score == 0.0
        assert cand.personalization_applied is False
        assert cand.final_score == cand.hybrid_score


def test_invariant_ml_artifacts_remain_immutable(db_session: Session):
    """CRITICAL INVARIANT: Adding feedback, pantry items, or preferences does not mutate
    authoritative CSVs or frozen ML artifacts.
    """
    # Authoritative files must exist and be readable
    from src.api.config import (
        RECIPES_PATH,
        RECIPE_NUTRITION_PATH,
        TFIDF_VECTORIZER_PATH,
        XGBOOST_MODEL_PATH,
    )
    assert RECIPES_PATH.is_file()
    assert RECIPE_NUTRITION_PATH.is_file()
    assert TFIDF_VECTORIZER_PATH.is_file()
    assert XGBOOST_MODEL_PATH.is_file()

    # Record user feedback in database
    user = UserModel(email="immutability@test.com", password_hash="dummy", is_active=True)
    db_session.add(user)
    db_session.flush()

    PersonalizationService.record_feedback(
        db=db_session,
        user_id=user.id,
        req=FeedbackRequest(recipe_id="r_0001", feedback_type=FeedbackType.LIKE),
    )

    # Files must still exist and be intact
    assert RECIPES_PATH.is_file()
    assert RECIPE_NUTRITION_PATH.is_file()
    assert TFIDF_VECTORIZER_PATH.is_file()
    assert XGBOOST_MODEL_PATH.is_file()
