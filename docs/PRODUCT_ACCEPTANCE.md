# KitchenPilot-V1 — Product Acceptance Criteria (Stage J)

## 1. Overview & Scope

This document specifies the authoritative, measurable acceptance criteria for **KitchenPilot-V1** in its Controlled Pilot and Production Validation phase (Stage J). KitchenPilot-V1 is the production prototype for the *Customized AI Kitchen for India (Intel Unnati-3)*.

System maturity requires satisfying four operational dimensions:
1. **Functional Correctness**
2. **Safety & Security Invariants**
3. **Reliability & Availability**
4. **Performance Baselines & Targets**
5. **Machine Learning Lifecycle Invariants**

---

## 2. Functional Correctness Acceptance Criteria

| Subsystem | Requirement / Invariant | Validation Method | Acceptance Threshold |
| :--- | :--- | :--- | :--- |
| **API Endpoints** | All 13 core operational routes respond with schema-conforming payloads. | `tests/test_api_contract.py`, `scripts/production_smoke_test.py` | 100% pass (0 contract regressions) |
| **Authentication Flow** | User registration, JWT issuance, token refresh, and login verification. Passwords securely hashed with bcrypt. | `tests/test_auth_endpoints.py`, `scripts/production_smoke_test.py` | 100% pass; 0 plaintext credentials stored or transmitted |
| **Personalization Engine** | User profiles, pantry items, and preferences isolate data strictly per authenticated user. | `tests/test_personalization.py`, `tests/test_production_smoke.py` | 0 cross-user leakages; isolated CRUD operations |
| **Recommendation Flow** | End-to-end pipeline: Candidate Retrieval $\rightarrow$ Hard Constraints $\rightarrow$ Hybrid Ranking $\rightarrow$ Personalization $\rightarrow$ Natural Language Explanation. | `scripts/production_smoke_test.py`, `tests/test_hybrid_ranker.py` | 100% deterministic response; explanation generated |
| **Feedback Funnel** | Real user interactions (`IMPRESSION`, `LIKE`, `SAVE`, `COOKED`, `DISLIKE`, `HIDE`) persisted to database with conflict precedence. | `scripts/check_feedback_readiness.py`, `scripts/export_interaction_dataset.py` | Precedence enforced: `HIDE > DISLIKE > COOKED > SAVE > LIKE > IMPRESSION`; 0 fabricated records |
| **Zero-Result Experience** | When strict dietary or nutritional constraints exclude all catalog items, a structured diagnostic with recovery guidance is returned. | `tests/test_constraint_engine.py`, `tests/test_production_smoke.py` | HTTP 200 with `diagnostics.primary_cause`, `safe_suggestions`, and zero constraint relaxation |
| **User Data Erasure** | Authenticated user can trigger full deletion of preferences, pantry, feedback, and history (`DELETE /api/v1/user/data`). | `tests/test_production_smoke.py` | 100% erasure of personal data; shared recipe catalog untouched |

---

## 3. Safety & Security Invariants

The following safety criteria are **hard invariants**. A single violation is an immediate release blocker:

1. **Zero Hard-Constraint Violations**:
   - Non-vegetarian, satvik-violating, jain-violating, or allergen-containing ingredients must NEVER appear in final recommendation results for a user or request with active constraints.
   - Hard constraints must ALWAYS execute before XGBoost ranking and personalization.
   - Hard constraints must NEVER be relaxed automatically to avoid zero results.

2. **Cross-User Data Isolation**:
   - No authenticated user may view, modify, or delete another user's preferences, pantry items, recommendation history, or interaction feedback.

3. **Credential & Secret Protection**:
   - Production environments (`ENVIRONMENT=production`) strictly reject default/dev secrets, requiring `AUTH_SECRET_KEY` with $\ge 32$ cryptographically secure characters.
   - Passwords must be hashed using bcrypt with salt rounds $\ge 12$. No passwords or access tokens are logged or returned in responses.

4. **Fabrication Prohibition**:
   - No synthetic, bootstrapped, or manufactured user feedback may ever be injected into the production interaction dataset or ML training set.

---

## 4. Reliability & Availability Criteria

| Criterion | Specification | Acceptance Threshold |
| :--- | :--- | :--- |
| **Application Startup** | System starts cleanly loading configuration, datasets, index vectors, and ML models. | Exit code 0, 0 unhandled boot exceptions |
| **Health & Readiness Probes** | `/health` reports process liveness; `/ready` verifies database connectivity and model artifact readiness. | Status 200 OK when components healthy; 503 Service Unavailable when core dependency down |
| **Deterministic Anonymous Flow** | Identical requests from unauthenticated visitors produce identical candidate rankings and explanations. | 100% reproducible baseline recommendations |
| **Controlled Error Handling** | Validation errors return structured HTTP 422 with field details; unhandled errors return generic 500 without leaking stack traces or internal paths to clients. | 0 internal exception traces leaked |

---

## 5. Performance Baselines & Target Thresholds

Stage H established empirical performance benchmarks on the production prototype hardware. The acceptance criteria separate observed baseline measurements from target operational SLA thresholds:

| Metric | Stage H Observed Baseline | Production Pilot Target Threshold | Target SLA |
| :--- | :--- | :--- | :--- |
| **Recommendation Latency (P50)** | 114 ms | $< 250$ ms | 99% of queries within threshold |
| **Recommendation Latency (P95)** | 179 ms | $< 500$ ms | 95% of queries within threshold |
| **Constraint Engine Latency (P95)**| 1.8 ms | $< 10$ ms | Evaluates 200 candidates |
| **Ranking Engine Latency (P95)** | 14.2 ms | $< 50$ ms | XGBoost 30-feature vector scoring |
| **API Error Rate** | 0.00% | $< 0.10\%$ | Errors / Total HTTP Requests |
| **Peak Memory Footprint** | ~580 MB | $< 1.5$ GB | Includes BGE vectors + TF-IDF index |

---

## 6. Machine Learning Lifecycle Invariant

> **CRITICAL ACCEPTANCE GATE**:
> **ML improvement cannot be declared until genuine interaction data satisfies the Stage I data sufficiency gates.**

Retraining or promoting candidate ranking models is strictly prohibited until the production database accumulates:
- $\ge 200$ unique genuine user interactions
- $\ge 20$ distinct registered users
- $\ge 50$ distinct recipes interacted with
- $\ge 30$ distinct query sessions
- $\ge 40$ positive engagement labels (`COOKED`, `SAVE`, `LIKE`)
- $\ge 10$ negative engagement labels (`DISLIKE`, `HIDE`)
- $\ge 7$ continuous days of collected data

Until all 7 criteria are met, `scripts/check_feedback_readiness.py` must return `INSUFFICIENT_DATA`, and the active model remains frozen as `xgb_ranker_v0.1.0`.
