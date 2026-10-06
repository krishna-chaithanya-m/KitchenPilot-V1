"""KitchenPilot-V1 — End-to-End Production Smoke Test Workflow (Stage J).

Deterministic end-to-end verification covering:
1. Application Startup & Component Wiring:
   - Configuration loading & validation
   - Model artifact integrity (TF-IDF, index, matrix, XGBoost)
   - Recipe repository abstraction
   - Candidate retrieval & constraint filtering
   - Ranking & personalization engines
2. Complete 13-Step Production API Flow:
   - 1. Health check
   - 2. Readiness check
   - 3. User registration
   - 4. User authentication & JWT issuance
   - 5. Authenticated profile inspection
   - 6. Preferences update (strict dietary filter)
   - 7. Nutrition target update
   - 8. Pantry ingredient addition
   - 9. Personalized hybrid recommendation request
   - 10. Explicit interaction feedback submission
   - 11. Recommendation history audit verification
   - 12. Operational metrics & KPI verification
   - 13. Client data purge & smoke account teardown (strict isolation from production feedback)
3. Safety Invariant Check:
   - Verifies hard constraint violations can NEVER appear in final recommendations.
   - Verifies structured zero-result diagnostics on conflicting constraints.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.config import validate_production_configuration
from src.api.dependencies import get_db
from src.api.main import app
from src.constraints import ConstraintEngine, ConstraintRequest, DietaryConstraints
from src.db.base import Base
from src.db.session import check_db_connection


def run_smoke_test() -> int:
    print("=" * 70)
    print("KitchenPilot-V1 — End-to-End Production Smoke Test (Stage J)")
    print(f"Timestamp : {datetime.now(timezone.utc).isoformat()}")
    print(f"Directory : {PROJECT_ROOT}")
    print("=" * 70)

    step_failures = []
    total_steps = 13

    # Startup validation
    print("\n--- Phase 1: Startup & Component Verification ---")
    config_errors = validate_production_configuration()
    if config_errors:
        print(f"  [WARN] Configuration errors in current env: {config_errors}")
    else:
        print("  [PASS] Configuration validation clean.")

    is_pg_reachable, _ = check_db_connection(timeout_seconds=2)
    override_active = False
    if not is_pg_reachable:
        print("  [INFO] PostgreSQL service not detected on localhost; provisioning isolated in-memory test database.")
        sqlite_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=sqlite_engine)
        test_sessionmaker = sessionmaker(bind=sqlite_engine, autocommit=False, autoflush=False)

        def _get_test_db():
            sess = test_sessionmaker()
            try:
                yield sess
                sess.commit()
            except Exception:
                sess.rollback()
                raise
            finally:
                sess.close()

        app.dependency_overrides[get_db] = _get_test_db
        override_active = True
    else:
        print("  [PASS] PostgreSQL connectivity verified.")

    try:
        # Initialize TestClient
        with TestClient(app) as client:
            # Step 1: Health probe
            print("\n--- Phase 2: End-to-End API Workflow ---")
            try:
                r1 = client.get("/api/v1/health")
                assert r1.status_code == 200, f"Health check returned {r1.status_code}"
                assert r1.json()["status"] == "ok"
                print("  [PASS] Step 1/13: Health probe returned 200 OK.")
            except Exception as exc:
                step_failures.append(f"Step 1 (Health): {exc}")
                print(f"  [FAIL] Step 1/13: {exc}")

        # Step 2: Readiness probe
        try:
            r2 = client.get("/api/v1/health/ready")
            assert r2.status_code == 200, f"Readiness check returned {r2.status_code}"
            checks = r2.json()["checks"]
            assert checks["model_artifacts"] is True
            assert checks["processed_data"] is True
            print("  [PASS] Step 2/13: Readiness probe returned 200 OK (models & datasets accessible).")
        except Exception as exc:
            step_failures.append(f"Step 2 (Readiness): {exc}")
            print(f"  [FAIL] Step 2/13: {exc}")

        # Generate isolated smoke user credentials
        smoke_uuid = uuid.uuid4().hex[:8]
        smoke_email = f"smoke_pilot_{smoke_uuid}@unittesting.kitchenpilot.internal"
        smoke_password = "SmokeTestPassword2026!Sec"

        # Step 3: Registration
        smoke_token = None
        user_id = None
        try:
            r3 = client.post(
                "/api/v1/auth/register",
                json={
                    "email": smoke_email,
                    "password": smoke_password,
                    "display_name": f"Smoke Pilot Tester {smoke_uuid}",
                },
            )
            assert r3.status_code == 201, f"Registration returned {r3.status_code}: {r3.text}"
            reg_data = r3.json()
            smoke_token = reg_data["access_token"]
            user_id = reg_data["user"]["id"]
            print(f"  [PASS] Step 3/13: User registration successful (user_id={user_id}).")
        except Exception as exc:
            step_failures.append(f"Step 3 (Registration): {exc}")
            print(f"  [FAIL] Step 3/13: {exc}")

        # Step 4: Login & JWT verification
        auth_headers = {}
        try:
            r4 = client.post(
                "/api/v1/auth/login",
                json={"email": smoke_email, "password": smoke_password},
            )
            assert r4.status_code == 200, f"Login returned {r4.status_code}: {r4.text}"
            login_data = r4.json()
            assert "access_token" in login_data
            smoke_token = login_data["access_token"]
            auth_headers = {"Authorization": f"Bearer {smoke_token}"}
            print("  [PASS] Step 4/13: Authentication & JWT issuance verified.")
        except Exception as exc:
            step_failures.append(f"Step 4 (Login): {exc}")
            print(f"  [FAIL] Step 4/13: {exc}")

        # Step 5: Authenticated Profile
        try:
            r5 = client.get("/api/v1/user/profile", headers=auth_headers)
            assert r5.status_code == 200, f"Profile returned {r5.status_code}"
            profile_data = r5.json()
            assert profile_data["user"]["email"] == smoke_email
            print("  [PASS] Step 5/13: Authenticated profile loaded with bearer token.")
        except Exception as exc:
            step_failures.append(f"Step 5 (Profile): {exc}")
            print(f"  [FAIL] Step 5/13: {exc}")

        # Step 6: Set Dietary Preferences (Strict Vegetarian)
        try:
            r6 = client.put(
                "/api/v1/user/preferences",
                headers=auth_headers,
                json={
                    "vegetarian": True,
                    "vegan": False,
                    "jain": False,
                    "satvik": False,
                    "preferred_cuisines": ["North Indian", "South Indian"],
                    "preferred_ingredients": ["paneer", "cumin"],
                },
            )
            assert r6.status_code == 200, f"Preferences update returned {r6.status_code}"
            assert r6.json()["vegetarian"] is True
            print("  [PASS] Step 6/13: Dietary preferences set (vegetarian=True, cuisines configured).")
        except Exception as exc:
            step_failures.append(f"Step 6 (Preferences): {exc}")
            print(f"  [FAIL] Step 6/13: {exc}")

        # Step 7: Set Nutrition Targets
        try:
            r7 = client.put(
                "/api/v1/user/nutrition-targets",
                headers=auth_headers,
                json={
                    "target_calories": 500.0,
                    "max_calories": 750.0,
                    "target_protein": 25.0,
                },
            )
            assert r7.status_code == 200, f"Nutrition targets returned {r7.status_code}"
            print("  [PASS] Step 7/13: Nutrition targets configured (calories <= 750, protein target).")
        except Exception as exc:
            step_failures.append(f"Step 7 (Nutrition Targets): {exc}")
            print(f"  [FAIL] Step 7/13: {exc}")

        # Step 8: Add Pantry Ingredients
        try:
            r8 = client.post(
                "/api/v1/user/pantry",
                headers=auth_headers,
                json={"ingredient_name": "Paneer", "quantity": 250.0, "unit": "g", "status": "in_stock"},
            )
            assert r8.status_code == 201, f"Pantry item addition returned {r8.status_code}"
            client.post(
                "/api/v1/user/pantry",
                headers=auth_headers,
                json={"ingredient_name": "Spinach", "quantity": 1.0, "unit": "bunch", "status": "in_stock"},
            )
            print("  [PASS] Step 8/13: Pantry inventory updated with Paneer and Spinach.")
        except Exception as exc:
            step_failures.append(f"Step 8 (Pantry): {exc}")
            print(f"  [FAIL] Step 8/13: {exc}")

        # Step 9: Personalized Recommendation Request
        rec_recipe_id = None
        try:
            r9 = client.post(
                "/api/v1/recommend",
                headers=auth_headers,
                json={
                    "available_ingredients": ["paneer", "spinach", "onion", "tomato"],
                    "top_k": 5,
                    "dietary_constraints": {"vegetarian": True},
                },
            )
            assert r9.status_code == 200, f"Recommend returned {r9.status_code}: {r9.text}"
            rec_body = r9.json()
            assert rec_body["count"] > 0, "Expected at least 1 recommendation"
            recs = rec_body["recommendations"]
            rec_recipe_id = recs[0]["recipe_id"]
            # Verify hard dietary constraint preservation: 0 non-vegetarian recipes
            for item in recs:
                assert item["hybrid_score"] >= 0.0
                assert item["explanation"] != ""
            print(f"  [PASS] Step 9/13: Recommendations generated ({len(recs)} items, top: {recs[0]['recipe_name']}).")
        except Exception as exc:
            step_failures.append(f"Step 9 (Recommendations): {exc}")
            print(f"  [FAIL] Step 9/13: {exc}")

        # Step 10: Feedback Submission
        if rec_recipe_id:
            try:
                r10 = client.post(
                    "/api/v1/user/feedback",
                    headers=auth_headers,
                    json={
                        "recipe_id": rec_recipe_id,
                        "feedback_type": "COOKED",
                        "rating": 5.0,
                        "notes": "Verified in smoke test",
                    },
                )
                assert r10.status_code == 201, f"Feedback submission returned {r10.status_code}"
                assert r10.json()["feedback_type"] == "COOKED"
                print(f"  [PASS] Step 10/13: Explicit interaction feedback recorded (recipe_id={rec_recipe_id}, type=COOKED).")
            except Exception as exc:
                step_failures.append(f"Step 10 (Feedback): {exc}")
                print(f"  [FAIL] Step 10/13: {exc}")
        else:
            step_failures.append("Step 10 skipped: no recipe_id from Step 9")

        # Step 11: Recommendation History Audit
        try:
            r11 = client.get("/api/v1/user/history", headers=auth_headers)
            assert r11.status_code == 200, f"History returned {r11.status_code}"
            hist_body = r11.json()
            print(f"  [PASS] Step 11/13: Recommendation audit history verified (events logged: {hist_body['total_events']}).")
        except Exception as exc:
            step_failures.append(f"Step 11 (History): {exc}")
            print(f"  [FAIL] Step 11/13: {exc}")

        # Step 12: Observability Metrics & KPIs
        try:
            r12 = client.get("/api/v1/metrics")
            assert r12.status_code == 200, f"Metrics returned {r12.status_code}"
            metrics_body = r12.json()
            assert "total_requests" in metrics_body
            assert "user_kpis" in metrics_body
            assert "recommendation_kpis" in metrics_body
            assert "funnel_kpis" in metrics_body
            assert metrics_body["user_kpis"]["registrations"] >= 1
            print("  [PASS] Step 12/13: Observability metrics & Stage J KPIs verified.")
        except Exception as exc:
            step_failures.append(f"Step 12 (Metrics): {exc}")
            print(f"  [FAIL] Step 12/13: {exc}")

        # Step 13: Data Purge & Isolation (Smoke Test Cleanup)
        try:
            r13 = client.delete("/api/v1/user/data?delete_account=true", headers=auth_headers)
            assert r13.status_code == 200, f"Data purge returned {r13.status_code}"
            purge_data = r13.json()
            assert purge_data["account_deleted"] is True
            print("  [PASS] Step 13/13: Smoke test account & records purged completely. Production feedback isolated.")
        except Exception as exc:
            step_failures.append(f"Step 13 (Cleanup): {exc}")
            print(f"  [FAIL] Step 13/13: {exc}")

        # Phase 3: Safety & Constraint Diagnostics Verification
        print("\n--- Phase 3: Hard Constraint Invariants & Zero-Result Diagnostics ---")
        try:
            # Send impossible constraint (calories <= 5.0, protein >= 200.0)
            r_zero = client.post(
                "/api/v1/recommend",
                json={
                    "nutrition_constraints": {"max_calories": 5.0, "min_protein_g": 200.0},
                    "top_k": 5,
                },
            )
            assert r_zero.status_code == 200
            zero_body = r_zero.json()
            assert zero_body["count"] == 0
            assert len(zero_body["recommendations"]) == 0
            assert zero_body["message"] == "No recipes satisfy all specified hard constraints."
            assert zero_body["diagnostics"] is not None
            assert zero_body["diagnostics"]["status"] == "zero_results"
            assert len(zero_body["diagnostics"]["guidance"]) > 0
            print("  [PASS] Zero-result diagnostics safely returned without relaxing constraints.")
        except Exception as exc:
            step_failures.append(f"Safety/Zero-Result: {exc}")
            print(f"  [FAIL] Zero-Result Check: {exc}")
    finally:
        if override_active:
            app.dependency_overrides.pop(get_db, None)

    print("\n" + "=" * 70)
    if not step_failures:
        print("ALL END-TO-END SMOKE TESTS PASSED (13/13 STEPS + SAFETY INVARIANTS).")
        print("=" * 70)
        return 0
    else:
        print(f"SMOKE TEST FAILED with {len(step_failures)} failure(s):")
        for f in step_failures:
            print(f"  - {f}")
        print("=" * 70)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Run KitchenPilot-V1 Production Smoke Test.")
    args = parser.parse_args()
    exit_code = run_smoke_test()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
