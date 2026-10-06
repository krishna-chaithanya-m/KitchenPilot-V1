# KitchenPilot-V1 — Controlled Deployment Pipeline (Stage J)

## 1. Overview & Operating Principles

The KitchenPilot-V1 deployment progression ensures that zero unverified code, configuration, or model changes reach staging or production environments. 

A deployment to production **must never occur merely because unit tests pass**. A production release requires passing through an explicit multi-stage gating pipeline.

```text
Local Development
        ↓
1. Unit & Regression Tests (`pytest -q`)
        ↓
2. Static Release Check (`scripts/release_check.py`)
        ↓
3. Automated Deployment Gate (`scripts/deployment_gate.py`)
        ↓
Staging Deployment
        ↓
4. End-to-End Production Smoke Test (`scripts/production_smoke_test.py`)
        ↓
5. API Contract Compliance Validation (`tests/test_api_contract.py`)
        ↓
6. Product Acceptance Criteria Sign-Off (`docs/PRODUCT_ACCEPTANCE.md`)
        ↓
Controlled Pilot (`PILOT_MODE=true`)
        ↓
Full Production
```

---

## 2. Mandatory Deployment Gates

Every gate is automated and blocking. If any gate fails, the pipeline aborts immediately.

### Gate 1: Unit & Regression Test Suite
- **Command**: `uv run pytest -q`
- **Scope**: All unit, integration, and security tests across `tests/`.
- **Pass Threshold**: 100% pass (0 failures, 0 regressions).

### Gate 2: Static Release Check
- **Command**: `uv run python scripts/release_check.py`
- **Scope**: Checks Python syntax, manifest consistency, data contracts, and static safety invariants.
- **Pass Threshold**: All checks exit with code 0.

### Gate 3: Automated Deployment Gate
- **Command**: `uv run python scripts/deployment_gate.py`
- **Scope**:
  1. Environment configuration validation (no dev secrets in prod, valid CORS, rate limiting enabled).
  2. Active model artifact (`models/ranking/xgboost_ranker.json`) and registry verification.
  3. Recipe catalog dataset and BGE semantic embeddings presence and checksum.
  4. Static release checks.
  5. End-to-end production smoke test execution.
  6. Feedback data sufficiency audit (`scripts/check_feedback_readiness.py`).

### Gate 4: Staging Deployment & Smoke Testing
- **Command**: `uv run python scripts/production_smoke_test.py`
- **Scope**: Deterministically simulates complete 13-step user workflow on real/staging database:
  - Startup & component wiring
  - Health & readiness probes
  - User registration & login
  - Profile preferences & nutrition targets
  - Pantry synchronization
  - Recommendation generation with natural language explanation
  - Feedback recording with conflict precedence
  - Zero-result diagnostic verification
  - User data purge verification

### Gate 5: API Contract Compliance Validation
- **Command**: `uv run pytest tests/test_api_contract.py -v`
- **Scope**: Validates OpenAPI contract compliance, strict Pydantic payload models, 401 unauthenticated enforcement, deterministic validation errors, and zero internal stack trace leakage.

### Gate 6: Controlled Pilot Activation
- **Configuration**:
  ```text
  ENVIRONMENT=production
  PILOT_MODE=true
  PILOT_MAX_USERS=50
  PILOT_INVITE_CODE=<secret_pilot_code>
  ```
- **Scope**: Allows a controlled cohort of real participants to use the application and record genuine interactions while keeping the ML ranker frozen at `xgb_ranker_v0.1.0`.

---

## 3. Deployment Checklist

Before initiating production deployment, the release operator must verify:

| Step | Verification Item | Command / Reference | Sign-off |
| :---: | :--- | :--- | :---: |
| 1 | Working tree clean | `git status --short` | [ ] |
| 2 | No whitespace/diff anomalies | `git diff --check` | [ ] |
| 3 | Full test suite passing | `uv run pytest -q` | [ ] |
| 4 | Deployment gate passing | `uv run python scripts/deployment_gate.py` | [ ] |
| 5 | Target database reachable | `uv run python scripts/init_db.py` | [ ] |
| 6 | Model checksums match registry | `uv run python scripts/model_registry_cli.py validate xgb_ranker_v0.1.0` | [ ] |
| 7 | Rollback plan prepared | `docs/ROLLBACK_RUNBOOK.md` | [ ] |
| 8 | Incident response contacts active | `docs/INCIDENT_RESPONSE.md` | [ ] |
