# KitchenPilot-V1 — Rollback Runbook (Stage J)

## 1. Overview & Core Philosophy

In production operations, rollback procedures must be **deterministic, fast, and safe**. This runbook outlines exact rollback workflows for code, database schemas, configurations, and machine learning models.

> **CRITICAL INVARIANT**:
> **Never implement or execute automatic ML rollback.** All ML promotions and rollbacks require explicit human operator approval and invocation.

---

## 2. Machine Learning Model Rollback

If a newly promoted model displays latency spikes, degraded user relevance, or scoring anomalies, follow this procedure to restore the previous active baseline model.

### 2.1 Audit Active Production Model
Check current production model version:
```powershell
uv run python scripts/model_registry_cli.py production
```

### 2.2 Execute Model Rollback
The model registry preserves the immediate predecessor in `models/ml_lifecycle/archive/`. Execute the atomic rollback command:
```powershell
uv run python scripts/model_registry_cli.py rollback
```

### 2.3 Verify Restored Model Integrity
```powershell
uv run python scripts/model_registry_cli.py validate xgb_ranker_v0.1.0
```

### 2.4 Restart API Workers
Restart the Uvicorn service to reload model weights into memory:
```powershell
# Windows PowerShell
Restart-Service kitchenpilot-api
# Or terminate and re-run:
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

---

## 3. Application Code & Configuration Rollback

### 3.1 Git Revision Rollback
To revert an unstable deployment to the previous tagged production release:
```powershell
# Identify previous release tag
git tag -l "v*"

# Checkout the previous stable release commit
git checkout v0.9.0-stage-i

# Re-install dependencies if dependencies changed
uv sync
```

### 3.2 Configuration Rollback
If a configuration change caused failures:
1. Revert `.env.production` to the backed-up copy (`.env.production.bak`).
2. Verify environment integrity:
   ```powershell
   uv run python -c "from src.api.config import Settings; s = Settings(); print('Environment:', s.ENVIRONMENT)"
   ```
3. Restart application service.

---

## 4. Database Schema Rollback

If a schema migration fails or causes data corruption:

### 4.1 Stop Incoming Traffic
Temporarily route traffic to a maintenance page or set `DATA_BACKEND=csv` to allow read-only recommendation traffic.

### 4.2 Point-in-Time Database Restoration
Restore the pre-deployment database dump (taken before the migration):
```powershell
pg_restore -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER -d $env:POSTGRES_DB --clean -v backups/pre_deployment_snapshot.dump
```

### 4.3 Verify Schema Integrity
```powershell
uv run python -c "
from src.db.session import get_db_session
from src.personalization.models import UserModel, UserPreferenceModel, UserPantryModel, UserFeedbackModel
with get_db_session() as db:
    print('Users:', db.query(UserModel).count())
    print('Feedback:', db.query(UserFeedbackModel).count())
"
```

---

## 5. Post-Rollback Validation Checklist

Always execute the complete verification suite after any rollback:

```powershell
# Step 1: Run End-to-End Production Smoke Test (13/13 steps)
uv run python scripts/production_smoke_test.py

# Step 2: Validate API Contract
uv run pytest tests/test_api_contract.py -v

# Step 3: Verify Health and Readiness
curl http://localhost:8000/health
curl http://localhost:8000/ready

# Step 4: Verify Data Sufficiency Gate
uv run python scripts/check_feedback_readiness.py
```
