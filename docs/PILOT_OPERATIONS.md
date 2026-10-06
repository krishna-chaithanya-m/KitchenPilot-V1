# KitchenPilot-V1 — Controlled Pilot Operations & Protocol (Stage K)

## 1. Operational Overview & Scope

This runbook defines the operational protocol for conducting the first controlled real-world pilot of **KitchenPilot-V1 (Customized AI Kitchen for India / Intel Unnati-3)**.

The pilot operates under strict constraints:
- **Maximum Cohort Capacity:** 50 authenticated real participants (`PILOT_MAX_USERS=50`).
- **Data Integrity Invariant:** Zero synthetic, fabricated, or bootstrapped interaction records.
- **Model Invariant:** Frozen production model `xgb_ranker_v0.1.0`. No online weight tuning or automated re-ranking.
- **Precedence Invariant:** Hard constraints strictly execute before ranking and personalization.

---

## 2. Phased Cohort Expansion Protocol

To prevent sudden operational degradation or unmonitored safety breaches, participant onboarding progresses through three controlled phases. **Automatic expansion between phases is strictly prohibited.** Advancement requires explicit manual review against formal promotion gates.

```text
Phase 1: Canary Cohort (5–10 participants)
              ↓ [Gate Review 1]
Phase 2: Expanded Cohort (10–25 participants)
              ↓ [Gate Review 2]
Phase 3: Full Pilot Cohort (25–50 participants)
```

### 2.1 Phase 1: Canary Pilot (5 to 10 Participants)
- **Objective:** Validate end-to-end user onboarding, preference persistence, pantry indexing, session impression generation, and feedback event submission in a small, closely observed group.
- **Duration:** Minimum 48 hours of active engagement.
- **Gating Requirements for Phase 2 Advancement:**
  1. `0` hard dietary or allergen constraint violations.
  2. `0` cross-user data leakage incidents.
  3. `0` authentication bypasses or unhandled 500 errors on user routes.
  4. Data quality audit returns `CLEAN` (`uv run python scripts/audit_pilot_data_quality.py`).
  5. API recommendation latency P95 < 1,200 ms.

### 2.2 Phase 2: Expanded Pilot (10 to 25 Participants)
- **Objective:** Evaluate session concurrency, database connection pool resilience, and query group diversity across diverse dietary preferences (Vegetarian, Vegan, Jain, Satvik).
- **Duration:** Minimum 5 consecutive calendar days.
- **Gating Requirements for Phase 3 Advancement:**
  1. All Phase 1 safety invariants strictly maintained at `0`.
  2. Zero-result rate < 5.0% across all genuine search and pantry queries.
  3. Interaction feedback funnel demonstrates active positive (`LIKE`, `SAVE`, `COOKED`) and negative (`DISLIKE`, `HIDE`) interactions.
  4. No duplicate feedback anomalies or inverted timestamps detected.

### 2.3 Phase 3: Full Pilot Cohort (25 to 50 Participants)
- **Objective:** Achieve sustained real-world usage across meals, build high-integrity interaction history, and evaluate progress toward Stage I ML data sufficiency thresholds.
- **Ceiling:** Hard limit of 50 users enforced at registration (`403 Forbidden: Pilot cohort capacity reached`).

---

## 3. Operational Monitoring & Cadence

| Activity | Frequency | Tool / Command | Owner |
|---|---|---|---|
| **Safety Invariant Verification** | Daily (09:00 UTC) | `uv run python scripts/verify_pilot_safety.py` | SRE / Safety Agent |
| **Data Quality Audit** | Every 12 Hours | `uv run python scripts/audit_pilot_data_quality.py --json` | ML Data Engineer |
| **Pilot KPI Reporting** | Daily | `uv run python scripts/generate_pilot_kpi_report.py` | Product Operations |
| **Stage I Readiness Check** | Weekly | `uv run python scripts/check_feedback_readiness.py` | ML Lead |
| **Database Parity & Health** | Daily | `uv run python scripts/validate_database_parity.py` | SRE |

---

## 4. Safety Gates & Pause / Kill Switch Criteria

The pilot must be **immediately paused** (`PILOT_MODE=false`) if any of the following triggers occur:
1. **Critical Safety Invariant Breach:** Any dietary rule failure (e.g., serving meat to a vegetarian) or allergen filter leak.
2. **Cross-User Data Exposure:** Any leaked profile, pantry, or history data across user IDs.
3. **Authentication Failure:** Token forgery, unauthenticated profile mutation, or invite code bypass.
4. **Data Corruption:** Batch temporal inversions (`feedback_timestamp < impression_timestamp`) or database schema corruption.

### 4.1 Non-Destructive Pause Execution
To pause pilot access without data loss:
```powershell
# 1. Disable pilot mode in environment configuration
$env:PILOT_MODE="false"

# 2. Reload API server workers
# (Existing users will receive 403 on new registrations; active sessions cannot enroll new accounts)

# 3. Execute safety audit
uv run python scripts/verify_pilot_safety.py
```
*Note: Pausing the pilot never deletes existing users, pantry inventories, or genuine interaction logs.*

---

## 5. ML Lifecycle Connection (Stage I Integration)

The pilot feeds genuine interactions directly into the Stage I evaluation pipeline. The dataset must strictly satisfy all conservative sufficiency thresholds before any candidate model can be evaluated:

| Sufficiency Gate | Required Threshold | Current Genuine Count | Gate Status |
|---|---|---|---|
| Total Interactions | `≥ 200` | Measured at runtime | Unmet until real usage |
| Unique Users | `≥ 20` | Measured at runtime | Unmet until real usage |
| Unique Recipes | `≥ 50` | Measured at runtime | Unmet until real usage |
| Unique Query Groups | `≥ 30` | Measured at runtime | Unmet until real usage |
| Positive Labels (`LIKE`/`SAVE`/`COOKED`) | `≥ 40` | Measured at runtime | Unmet until real usage |
| Negative Labels (`DISLIKE`/`HIDE`) | `≥ 10` | Measured at runtime | Unmet until real usage |
| Temporal Span (Days of Data) | `≥ 7 days` | Measured at runtime | Unmet until real usage |

**Authoritative ML Status Prior to Meeting All Gates:**
```text
INSUFFICIENT_DATA
```
Even when all gates are met, the status transitions to:
```text
READY_FOR_EVALUATION
```
**Automated model promotion to production is strictly forbidden.** Model promotion requires offline evaluation, candidate comparison, and explicit human sign-off per `docs/ML_LIFECYCLE.md`.

---

## 6. Pilot Completion & Stage K Acceptance Criteria

Stage K does not end simply because code runs without errors. Formal conclusion of Stage K requires satisfying all four invariant domains:

### 6.1 Functional Acceptance
- [x] End-to-end first-run onboarding completes successfully (Register → Preferences → Targets → Pantry → Recommendations → Feedback).
- [x] Implicit session impressions (`IMPRESSION = 1`) logged automatically upon rendering results.
- [x] Explicit feedback (`LIKE`, `SAVE`, `COOKED`, `DISLIKE`, `HIDE`) correctly recorded with associated `session_id`.
- [x] User account deactivation self-service works cleanly and halts access immediately.

### 6.2 Safety Acceptance
- [x] Hard constraint violations: `0`
- [x] Cross-user data leakage: `0`
- [x] Authentication bypasses: `0`
- [x] Secret leakage: `0`
- [x] Feedback fabrication: `0`
- [x] Unauthorized pilot access: `0`

### 6.3 Operational Acceptance
- [x] Non-destructive pilot kill switch verified (`PILOT_MODE=false`).
- [x] Playbook P1–P7 documented in `docs/INCIDENT_RESPONSE.md`.
- [x] Automated KPI dashboard generating genuine metrics with `NO_DATA` handling.
- [x] Rollback runbook verified against registered baseline `xgb_ranker_v0.1.0`.

### 6.4 Data & ML Integrity Acceptance
- [x] Genuine feedback collection pipeline operational without synthetic data.
- [x] Feedback data quality audit reporting `CLEAN`.
- [x] Authoritative ML status explicitly reported as `INSUFFICIENT_DATA` until sufficiency thresholds are met.
- [x] Freeze protocol active on model weights, feature schema (30 features), and retrieval pipelines.
