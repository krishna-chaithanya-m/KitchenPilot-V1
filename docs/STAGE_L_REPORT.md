# KitchenPilot-V1 — Stage L Comprehensive Report: Canary Pilot Execution, Real-User Data Collection & Evidence-Based Evaluation

**Document Identifier:** `KP-STAGE-L-REPORT-2026`  
**Execution Timestamp:** `2026-10-04T18:49:00+05:30`  
**Application Version:** `1.0.2`  
**Git Commit Hash:** `f5f48d091701e71542acb0a74bdd98a65fe12398`  
**Active Production Model:** `xgb_ranker_v0.1.0` (FROZEN)  
**Safety Protocol:** Strict Zero-Tolerance Hard Constraints, Zero Data Leakage, Zero Synthetic Data  

---

## 1. Pilot Objective

The primary objective of **Stage L** is the execution of the first real-user canary pilot for **KitchenPilot-V1 (Customized AI Kitchen for India / Intel Unnati-3)**.

Stage K established that all required pilot infrastructure, enrollment gates, deactivation controls, and session-linked feedback pipelines were production-ready. Stage L transitions from **pilot infrastructure preparation** to **actual controlled participant operation and evidence collection**.

The governing goal of Stage L is:
> **Collect trustworthy real-world interaction data while validating product behavior, recommendation usefulness, safety, reliability, and user experience.**

In accordance with strict project rules:
- **No synthetic users or fabricated interactions** were created.
- The active ML ranking model (`xgb_ranker_v0.1.0`), semantic retrieval indexes (`bge-small-en-v1.5`), and recipe catalogs remain completely **FROZEN**.
- Stage L establishes the empirical data-collection phase without premature retraining or unvalidated model changes.

---

## 2. Baseline Version

Prior to canary activation, an immutable snapshot was created and recorded in [`docs/CANARY_BASELINE.md`](file:///c:/Python/KitchenPilot-V1/docs/CANARY_BASELINE.md):

| Category | Component | Identifier / Version | SHA256 Checksum |
|---|---|---|---|
| **Application** | Backend API | `1.0.2` (Git `f5f48d091701e71542acb0a74bdd98a65fe12398`) | — |
| **Runtime** | Python | `3.14.5` (64-bit AMD64) | — |
| **Dataset** | Master Recipes | `1.0.0` (6,871 recipes) | `008d75ae96cc580c96d2244a73b06017fc09c36192f34a265b0c520e3a0ae64d` |
| **Dataset** | Nutrition Profiles | `1.0.0` (CNF 2026 linked) | `84a2fdb8dabb75aeb4296554110c572a198271f23bba7a06c30a1df9d4fc3ff1` |
| **Dataset** | Ingredient Links | `1.0.0` (62,000+ links) | `edc9ced314a1724330cef4c896b314d9f9614640ca5de39780192c69a89efb6c` |
| **Dataset** | Normalized Ingredients| `1.0.0` (1,400+ ontology items) | `8d9d81a8ea9570709e4bde040d4d52bc1f3fcc4087e7dff6d60f76555f962fe8` |
| **Retrieval** | Lexical TF-IDF Vectorizer | Scikit-Learn `(1, 2)` n-grams | `17b27006a1712bb8edb5c29cf4e60152d2690d4d32c5761ebc202ad722758bbd` |
| **Retrieval** | TF-IDF Matrix | Sparse Compressed NPZ | `c7ce7d50028c876fe2835453d85bc0686eb1bf8e8469652bdcf74a0a43794793` |
| **Retrieval** | Dense Semantic Index | `BAAI/bge-small-en-v1.5` (384-dim) | `1423c5e233a5decdd7e6b90879c7b25166d158bcbf805336f0354f04f47ca382` |
| **Ranking** | GBDT Ranker | `xgb_ranker_v0.1.0` (30 features) | `8d00370fb80f81de6e889a1c6b75290063284a3964de85a2a9acc502b0d6677b` |
| **Personalization** | Reranker Weight | $\lambda = 0.20$ | Deterministic cosine/affinity |

---

## 3. Cohort Size & Pilot Capacity

| Cohort Configuration | Parameter | Value | Operational Status |
|---|---|---|---|
| **Canary Phase Target** | Phase 1 | `5–10 real participants` | Active Target |
| **Cohort Hard Ceiling** | `PILOT_MAX_USERS` | `50` | Enforced at registration |
| **Pilot Mode Toggle** | `PILOT_MODE` | `true` | Controlled pilot gating |
| **Enrolled Real Participants** | Registered Users | `0` | Clean genuine start |
| **Available Slots** | Remaining Capacity | `50` | Open for Phase 1 invitees |

---

## 4. Participant Onboarding Protocol

The system provides a privacy-first onboarding flow without collecting medical information or unnecessary personal data:

```text
1. Invite Distribution (Controlled Cohort Code)
         ↓
2. Pilot Notice & Disclosure (Voluntary Research Prototype, Non-Medical Advice)
         ↓
3. Consent / Acknowledgement
         ↓
4. Registration (Minimal: Email, Password, Optional Display Name, Invite Code)
         ↓
5. Authenticated Login (Argon2id + JWT Bearer Token)
         ↓
6. Preference Configuration (Vegetarian, Vegan, Jain, Satvik, Cuisines, Regions)
         ↓
7. Nutrition Targets (Optional: Daily / Meal Macro Goals)
         ↓
8. Pantry Setup (Ingredient Names mapped via Canonical Ontology)
         ↓
9. First Recommendation Query (Hybrid Dense + Lexical Fusion)
```

The system explicitly informs users:
> *"Nutritional data and recipe suggestions are for culinary and informational purposes only and do NOT constitute medical diagnosis or clinical dietary guidance."*

---

## 5. Actual Genuine Interaction Count

All metrics are measured directly from the database using [`scripts/audit_pilot_data_quality.py`](file:///c:/Python/KitchenPilot-V1/scripts/audit_pilot_data_quality.py):

| Metric | Genuine Measurement |
|---|---|
| **Total Genuine Interactions** | **`0`** |
| **Raw Synthetic / Bootstrapped Interactions** | **`0`** (Strictly Prohibited) |
| **Total Logged Impressions (`IMPRESSION`)** | **`0`** |
| **Total Explicit Feedback Events** | **`0`** |

---

## 6. Unique Users

| Metric | Genuine Measurement | Sufficiency Gate Requirement | Status |
|---|---|---|---|
| **Registered Real Users** | **`0`** | `≥ 20` | Gate Blocked |
| **Active Users with Feedback** | **`0`** | `≥ 20` | Gate Blocked |

---

## 7. Unique Recipes with Feedback

| Metric | Genuine Measurement | Sufficiency Gate Requirement | Status |
|---|---|---|---|
| **Distinct Recipes with Feedback** | **`0`** | `≥ 50` | Gate Blocked |
| **Total Recipes in Catalog** | `6,871` | Available for retrieval | Ready |

---

## 8. Query Groups

| Metric | Genuine Measurement | Sufficiency Gate Requirement | Status |
|---|---|---|---|
| **Distinct Recommendation Query Sessions** | **`0`** | `≥ 30` | Gate Blocked |

---

## 9. Date Range

| Parameter | Value |
|---|---|
| **Date Range Start** | `NO_DATA` |
| **Date Range End** | `NO_DATA` |
| **Calendar Days of Data** | `0.0 days` (Requires `≥ 7 days` for ML evaluation) |

---

## 10. Positive Labels

Positive labels follow Stage I relevance grading (`LIKE` = grade 2, `SAVE` = grade 2, `COOKED` = grade 3):

| Feedback Type | Relevance Grade | Measured Count |
|---|---|---|
| `LIKE` | 2 | `0` |
| `SAVE` | 2 | `0` |
| `COOKED` | 3 | `0` |
| **Total Positive Labels** | **2 or 3** | **`0`** (Requires `≥ 40` for ML evaluation) |

---

## 11. Negative Labels

Negative labels follow Stage I relevance grading (`DISLIKE` = grade 0, `HIDE` = grade 0):

| Feedback Type | Relevance Grade | Measured Count |
|---|---|---|
| `DISLIKE` | 0 | `0` |
| `HIDE` | 0 | `0` |
| **Total Negative Labels** | **0** | **`0`** (Requires `≥ 10` for ML evaluation) |

---

## 12. Engagement Funnel

Measured from runtime interaction history:

```text
Recommendation Request : NO_DATA
        ↓
    Impression         : 0
        ↓
    Engagement (Like)  : 0
        ↓
    Save (Favorite)    : 0
        ↓
    Cooked             : 0
```

---

## 13. Data-Quality Audit

Automated execution via `uv run python scripts/audit_pilot_data_quality.py`:

| Audit Check | Measured Value | Standard / Invariant | Status |
|---|---|---|---|
| **Overall Quality Status** | `CLEAN` | `CLEAN` or `ACCEPTABLE` | **PASS** |
| **Duplicate Events** | `0` | Must be 0 | **PASS** |
| **Invalid User IDs** | `0` | Must be 0 | **PASS** |
| **Invalid Recipe IDs** | `0` | Must be 0 | **PASS** |
| **Temporal Violations** | `0` | Must be 0 | **PASS** |
| **Missing Query Groups** | `0` | Must be 0 | **PASS** |
| **Conflicting Feedback Pairs** | `0` | Must be 0 | **PASS** |
| **Detected Anomalies** | `[]` | Empty list | **PASS** |

---

## 14. Safety Audit

Automated execution via `uv run python scripts/verify_pilot_safety.py`:

| Safety Invariant | Measured Value | Target | Outcome |
|---|---|---|---|
| **Hard Constraint Violations** | `0` | `0` | **PASS** (Zero tolerance verified) |
| **Cross-User Data Leakage** | `0` | `0` | **PASS** (Token boundaries enforced) |
| **Authentication Bypasses** | `0` | `0` | **PASS** (401 on unauthorized access) |
| **Secret Exposures** | `0` | `0` | **PASS** (No secrets in API responses) |
| **Feedback Fabrication** | `0` | `0` | **PASS** (Zero synthetic/orphaned records) |
| **Pilot Capacity Enforcement** | `50` | `50` | **PASS** (Enforced at registration) |
| **Kill Switch Functionality** | Clean | Non-destructive | **PASS** (Non-destructive blocking) |

---

## 15. Performance & Latency Observations

Measurements adhere to the strict rule: *If a metric is unmeasured, report `NO_DATA`. Do not substitute zero.*

| Metric | Measured Value | SLA Target | Status |
|---|---|---|---|
| **Recommendation Latency P50** | `NO_DATA` | < 500 ms | Awaiting real user traffic |
| **Recommendation Latency P95** | `NO_DATA` | < 1,200 ms | Awaiting real user traffic |
| **Database Latency P50** | `NO_DATA` | < 50 ms | Awaiting real user traffic |
| **Retrieval Latency P50** | `NO_DATA` | < 250 ms | Awaiting real user traffic |
| **Ranking Latency P50** | `NO_DATA` | < 50 ms | Awaiting real user traffic |

*Note: Benchmarked cold/warm endpoint latency from Stage H verified P95 < 600 ms in synthetic test environments. Actual real-world pilot latencies will be recorded as genuine participant traffic arrives.*

---

## 16. User Experience Feedback (Qualitative Mechanism)

As specified in **Section 11 (L10)**, a lightweight qualitative feedback mechanism was implemented to capture unstructured user experience commentary without contaminating the ML training datasets:

### Implementation:
- **Database Model:** [`QualitativeFeedbackModel`](file:///c:/Python/KitchenPilot-V1/src/personalization/models.py) (`qualitative_feedback` table).
- **Supported Issue Types:**
  - `recommendation_irrelevant`
  - `missing_ingredient`
  - `wrong_dietary_match`
  - `nutrition_information_issue`
  - `poor_explanation`
  - `slow_response`
  - `confusing_ui`
  - `useful_recommendation`
  - `other_issue`
- **Endpoints:**
  - `POST /api/v1/user/qualitative-feedback`
  - `GET /api/v1/user/qualitative-feedback`
- **UI Integration:** Recommendation cards include a `"💬 Issue"` button triggering categorized participant reporting.
- **Privacy & Purge:** User data erasure (`DELETE /api/v1/user/data`) purges qualitative commentary along with all other profile artifacts.
- **Separation Invariant:** Qualitative feedback is verified **never** to enter the ML training interaction set or affect relevance labels automatically.

### Early Qualitative Themes:
- `NO_DATA` (Canary cohort onboarding commencing).

---

## 17. Incidents & Non-Destructive Pause Events

| Category | Count | Details |
|---|---|---|
| **Critical Safety Incidents** | `0` | Zero dietary/allergen failures. |
| **Data Leakage Incidents** | `0` | Zero cross-user exposures. |
| **Production Halts / Pauses** | `0` | Kill switch verified ready; no emergency halt required. |

---

## 18. Cohort Expansion Decision

| Phased Cohort | Size | Status | Advancement Decision |
|---|---|---|---|
| **Phase 1: Canary Pilot** | 5–10 users | **ACTIVE** | Currently in initial deployment. |
| **Phase 2: Expanded Pilot** | 10–25 users | **BLOCKED** | Hold until Phase 1 achieves ≥ 48h active engagement without incidents. |
| **Phase 3: Full Pilot** | 25–50 users | **BLOCKED** | Hold until Phase 2 criteria are satisfied. |

**Formal Decision:** **MAINTAIN PHASE 1 (5–10 PARTICIPANTS)**. Automatic cohort expansion is strictly prohibited. Advancement requires accumulated multi-day operational evidence.

---

## 19. Stage I ML Readiness Status

Automated audit via `uv run python scripts/check_feedback_readiness.py`:

```text
--- Current Data Sufficiency Gate Status ---
Status: INSUFFICIENT_DATA
Is Sufficient for ML Retraining: False

Parameter Threshold Comparison:
  Total Interactions :     0 / 200 required  [BLOCKED]
  Unique Users       :     0 / 20 required   [BLOCKED]
  Unique Recipes     :     0 / 50 required   [BLOCKED]
  Unique Queries     :     0 / 30 required   [BLOCKED]
  Positive Labels    :     0 / 40 required   [BLOCKED]
  Negative Labels    :     0 / 10 required   [BLOCKED]
  Days of Data       :   0.0 / 7.0 days req  [BLOCKED]
```

**Status:** **`INSUFFICIENT_DATA`**. Under the governing ML Lifecycle policy, no model retraining, comparison, or promotion is authorized.

---

## 20. Current Production Model

- **Model ID:** `xgb_ranker_v0.1.0`
- **Algorithm:** XGBoost Pairwise Ranking (LambdaMART)
- **Status:** **ACTIVE PRODUCTION (FROZEN)**
- **Feature Vector:** 30 Features (`v1.0.0`)
- **Checksum:** `8d00370fb80f81de6e889a1c6b75290063284a3964de85a2a9acc502b0d6677b`

---

## 21. Evaluation Results Against Genuine Interactions

Because the genuine interaction dataset currently has 0 interactions (`INSUFFICIENT_DATA`), running an offline evaluation pipeline on empty data would produce invalid, deceptive, or non-deterministic metrics.

In strict adherence to **Section 1 (Non-Negotiable Rules)** and **Section 20 (L19)**:
- Evaluation metrics against genuine user feedback: **`NO_DATA`**.
- Offline baseline remains anchored to the frozen Stage I benchmark:
  - NDCG@5: `0.8841`
  - NDCG@10: `0.9126`
  - MRR@10: `0.9412`

---

## 22. Known Limitations

1. **Early Canary Cold-Start:** Initial cohort participants will rely primarily on sparse/dense retrieval fusion, dietary hard filtering, and cold-start heuristic personalization until natural feedback history builds.
2. **PostgreSQL Service Offline in Local Dev:** The local development environment operates against SQLite/in-memory ORM test databases; production deployment requires PostgreSQL 15+ containerization (`docker-compose.yml`).
3. **Sparse Feedback Volume:** Statistical significance cannot be claimed until all 7 Stage I sufficiency thresholds are fulfilled over multiple calendar days.

---

## 23. Recommendation for Next Stage

1. **Continue Phase 1 Canary Operations:** Onboard the first 5–10 real participants using controlled invite codes.
2. **Execute Daily Audits:** Run `scripts/verify_pilot_safety.py` and `scripts/audit_pilot_data_quality.py` on the established daily schedule.
3. **Monitor Qualitative Feedback:** Review participant UX submissions via `/api/v1/user/qualitative-feedback` to identify usability or explanation clarity issues.
4. **Enforce Frozen ML Policy:** Maintain `xgb_ranker_v0.1.0` in production without modification until Stage I data sufficiency gates report `READY_FOR_EVALUATION`.
5. **No Automatic Retraining or Promotion:** Do not attempt candidate retraining or promotion until empirical sufficiency and offline gate checks are fully satisfied.
