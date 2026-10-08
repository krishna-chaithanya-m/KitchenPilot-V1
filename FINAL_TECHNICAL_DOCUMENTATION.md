# KitchenPilot-V1 — Final Technical Documentation

**System Title:** KitchenPilot-V1: Deterministic, Explainable Personalized Indian Recipe Recommendation Engine
**Project Track:** Customized AI Kitchen for India (Intel Unnati-3)
**Release Version:** 1.0.0
**Production Commit:** `a35e84a`
**Date of Technical Audit:** October 8, 2026
**Operational Status:** PRODUCTION READY — REAL PILOT DATA COLLECTION PENDING

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Objectives](#3-objectives)
4. [System Architecture](#4-system-architecture)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Backend Architecture](#6-backend-architecture)
7. [Database Architecture](#7-database-architecture)
8. [Data Processing Pipeline](#8-data-processing-pipeline)
9. [Dataset Description](#9-dataset-description)
10. [Ingredient Ontology](#10-ingredient-ontology)
11. [Recommendation Pipeline](#11-recommendation-pipeline)
12. [Ingredient Matching](#12-ingredient-matching)
13. [TF-IDF / Similarity Method](#13-tf-idf--similarity-method)
14. [Nutrition Scoring](#14-nutrition-scoring)
15. [Hybrid Ranking](#15-hybrid-ranking)
16. [XGBoost Ranking Model](#16-xgboost-ranking-model)
17. [Personalization](#17-personalization)
18. [Hard Constraint Engine](#18-hard-constraint-engine)
19. [Recommendation Explainability](#19-recommendation-explainability)
20. [Feedback System](#20-feedback-system)
21. [Recommendation History](#21-recommendation-history)
22. [Authentication and Authorization](#22-authentication-and-authorization)
23. [Security Controls](#23-security-controls)
24. [API Endpoints](#24-api-endpoints)
25. [Docker Architecture](#25-docker-architecture)
26. [Azure Deployment Architecture](#26-azure-deployment-architecture)
27. [Production Configuration](#27-production-configuration)
28. [Testing Strategy](#28-testing-strategy)
29. [Test Results](#29-test-results)
30. [Production Verification](#30-production-verification)
31. [Pilot Mode](#31-pilot-mode)
32. [Current Pilot Status](#32-current-pilot-status)
33. [Known Limitations](#33-known-limitations)
34. [Future Work](#34-future-work)
35. [Final Release Information](#35-final-release-information)

---

## 1. Project Overview

KitchenPilot-V1 is an offline-capable, deterministic, personalized recipe recommendation and nutrition analysis platform specifically engineered for Indian cuisine. Developed under the Intel Unnati-3 initiative ("Customized AI Kitchen for India"), the system provides a production-grade web application backed by a high-throughput FastAPI engine, audited culinary databases, and macro/micronutrient profiles anchored to the Canadian Nutrient File (CNF 2026).

The platform emphasizes algorithmic transparency, deterministic tie-breaking, strict dietary compliance (Vegetarian, Vegan, Jain root-vegetable restrictions, and Satvik culinary traditions), and transparent explanations.

---

## 2. Problem Statement

Indian culinary preparation features profound regional diversity, nuanced ingredient substitutions, and strict cultural/religious dietary restrictions. Modern recipe applications typically suffer from several foundational flaws:
1. **Opaque Recommendations**: Black-box generative models frequently recommend recipes that violate strict dietary taboos (e.g., suggesting onions or garlic to a Jain user or dairy to a vegan).
2. **Food Waste**: Inability to match available household pantry items against complex culinary variants and regional aliases.
3. **Unvalidated Nutritional Claims**: Nutritional values in user-contributed recipe portals are notoriously fabricated or inconsistent.
4. **Lack of Explainability**: Systems fail to communicate *why* a particular dish was chosen relative to pantry coverage or user goals.

---

## 3. Objectives

- **Deterministic Constraint Enforcement**: Ensure hard dietary filters (Vegetarian, Vegan, Jain, Satvik, Allergens) are strictly applied *before* candidate scoring and ranking.
- **Canonical Ingredient Ontology**: Map thousands of raw culinary text variants, colloquial terms, and regional aliases to verified canonical ingredients.
- **Scientific Nutrition Profiling**: Calculate energy and macronutrient profiles per recipe and serving using frozen CNF 2026 reference standards without live external dependencies.
- **Hybrid & GBDT Ranking**: Balance text similarity, ingredient coverage, nutritional fit, and user preferences using a four-pillar scoring engine and frozen XGBoost Learning-to-Rank inference.
- **Privacy-Preserving Personalization**: Personalize recommendations using explicit user interactions and persistent pantry items while enforcing strict token boundaries and zero cross-user data leakage.
- **Controlled Pilot Infrastructure**: Deploy a robust, audited production container on Azure Container Apps with complete telemetry, correlation tracking, rate limiting, and automated health monitoring.

---

## 4. System Architecture

```text
[ Client Browser (Vanilla HTML/CSS/JS) ]
                 │
                 ▼ HTTPS
[ Azure Container Apps: Ingress (Port 8000) ]
                 │
                 ▼
[ Middleware: Correlation ID (X-Request-ID) + Security Headers + Rate Limiting ]
                 │
                 ├──► [ Liveness & Readiness Probes: /health, /health/ready ]
                 │
                 ▼
[ Authentication & Authorization: Argon2id + PyJWT (Bearer Token) ]
                 │
                 ├──► [ User Data Isolation: Profile, Pantry, History, Feedback ]
                 │
                 ▼
[ Recommendation Orchestrator (KitchenPilotRecommender) ]
                 │
                 ├──► 1. Stage E Constraint Engine (Dietary, Allergens, Required/Excluded)
                 │         │ (Pre-Filtering & Conflict Detection)
                 │         ▼
                 ├──► 2. Candidate Retrieval Layer
                 │         ├─ TF-IDF Vectorizer + Sparse Matrix (Default)
                 │         └─ Dense Semantic Retrieval: BAAI/bge-small-en-v1.5 (Optional)
                 │         ▼
                 ├──► 3. Four-Pillar Scoring
                 │         ├─ Pillar 1: Similarity Score (Lexical or Semantic)
                 │         ├─ Pillar 2: Ingredient Matching (Coverage & Jaccard)
                 │         ├─ Pillar 3: Nutrition Scoring (Multi-Goal CNF 2026)
                 │         └─ Pillar 4: Preference Compatibility (Cuisine/Region/Meal)
                 │         ▼
                 ├──► 4. Ranking Dispatcher
                 │         ├─ Primary: XGBoost Ranker (xgb_ranker_v0.1.0, rank:ndcg)
                 │         └─ Fallback: Deterministic HybridRanker
                 │         ▼
                 ├──► 5. Stage G Personalization Adjustments
                 │         │ (Applies preference boosts & interaction history weights)
                 │         ▼
                 ├──► 6. Deterministic Tie-Breaking
                 │         ▼
                 ├──► 7. Explainability Generator (Deterministic Templates)
                 │         ▼
                 └──► 8. Audit Event Logging (Recommendation History & Metrics)
```

---

## 5. Frontend Architecture

The frontend is a lightweight, responsive static web application located in `frontend/`. It uses vanilla HTML5, CSS3, and modern modular JavaScript without heavy frameworks, maximizing performance and compatibility.

### 5.1 Pages and Views
- `frontend/index.html`: Hero landing page, architectural pillars overview, and live dynamic backend connectivity status indicator.
- `frontend/recipes.html`: Searchable recipe catalog with pagination, cuisine filters, meal types, and dietary checkboxes.
- `frontend/recipe.html`: Detailed recipe view displaying prep/cook times, servings, full ingredients list, step-by-step instructions, and nutrient breakdown.
- `frontend/recommendations.html`: Interactive recommendation studio supporting pantry tag management, dietary preferences, nutritional target inputs, pilot participant login/registration, and explicit interaction feedback.

### 5.2 Dynamic Configuration Architecture (`config.js`)
To enable seamless transitions between local testing and production verification, `frontend/js/config.js` implements prioritized target resolution:
1. **URL Query Parameters**: `?env=dev` (targets `http://127.0.0.1:8000/api/v1`) or `?env=prod` (targets Azure Container Apps).
2. **Local Storage**: `localStorage.getItem("kitchenpilot_api_base_url")`.
3. **Window Global**: `window.KITCHENPILOT_API_BASE_URL`.
4. **Default Production Target**: `https://kitchenpilot-api.whitestone-ffca5e6e.malaysiawest.azurecontainerapps.io/api/v1`.

### 5.3 JavaScript Client Modules
- `frontend/js/api.js`: Centralized API client exposing `KitchenPilotApi` on `window`, handling JSON serialization, JWT authorization header injection, unified error parsing (`ApiError`), and environment URL resolution (`getApiBaseUrl`, `setApiBaseUrl`).
- `frontend/js/app.js`: Dynamic home page health and readiness poller.
- `frontend/js/recipes.js`: Catalog pagination and filter query controller.
- `frontend/js/recipe.js`: Recipe detail loader and similar-recipe trigger.
- `frontend/js/recommendations.js`: Tagged ingredient input, pilot authentication box, pantry synchronization, and feedback buttons.

---

## 6. Backend Architecture

The backend is built with **FastAPI (0.115+)** running on **Uvicorn (0.30+)** under **Python 3.12**.

### 6.1 Lifecycle & Startup Management (`src/api/main.py`)
Application startup utilizes FastAPI's `lifespan` context manager:
1. Validates production configuration (`validate_production_configuration`).
2. Instantiates and warms the singleton `KitchenPilotRecommender`.
3. Loads and indexes recipe and nutrition catalogs via the repository abstraction (`RecipeStore`).
4. Logs catalog counts and verification state.

### 6.2 Middleware Stack (`src/api/middleware.py`)
1. **Request Correlation**: Extracts or generates an `X-Request-ID` (`req_<hex16>`) preserved throughout the call chain.
2. **Security Headers**: Injects `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, and `Referrer-Policy: strict-origin-when-cross-origin`.
3. **In-Memory Rate Limiting**: Sliding-window rate limiter per client IP and route category (`RATE_LIMIT_AUTH_RPM=20`, `RATE_LIMIT_RECOMMEND_RPM=60`, `RATE_LIMIT_FEEDBACK_RPM=60`, `RATE_LIMIT_GLOBAL_RPM=120`). Rejections return `HTTP 429 Too Many Requests` with a `Retry-After` header.
4. **CORS Middleware**: Configured via `ALLOWED_ORIGINS` with strict credential support. Production validation prohibits wildcard `*` origins when credentials are enabled.
5. **Observability**: Real-time metrics collector exposed at `GET /api/v1/metrics`.

---

## 7. Database Architecture

The persistence layer uses **SQLAlchemy 2.0** ORM supporting both PostgreSQL (via `psycopg` v3) and in-memory/CSV backends via repository abstractions.

### 7.1 Relational Schema & Tables
1. **Catalog Domain (`src/db/models.py`)**:
   - `recipes`: Primary recipe entity (`recipe_id`, names, times, servings, dietary flags, source metadata).
   - `ingredients`: Canonical ingredient entities (`ingredient_id`, `canonical_name`, category, flags).
   - `ingredient_aliases`: Synonym mapping table (`alias_id`, `canonical_ingredient_id`, `alias`, `confidence`).
   - `recipe_ingredients`: Relational linkage (`recipe_id`, `ingredient_id`, original text, mapping status).
   - `recipe_nutrition`: Per-recipe aggregate energy and nutrient totals and per-serving amounts.
   - `recipe_ingredient_nutrition`: Granular item-level nutrient calculations, food codes, and gram mass.
   - `dataset_manifest_metadata`: Provenance checksums, row counts, and schema versions.
2. **Personalization Domain (`src/personalization/models.py`)**:
   - `users`: User accounts (`id`, `email`, `password_hash`, `is_active`, timestamps).
   - `user_preferences`: Dietary preferences, preferred/disliked ingredients, cuisines, regions, meal types.
   - `user_nutrition_targets`: Daily/per-meal targets (calorie bounds, macronutrient minima/maxima).
   - `user_pantry`: Persistent ingredient inventory mapped to canonical IDs.
   - `user_feedback`: Explicit interaction events (`LIKE`, `DISLIKE`, `SAVE`, `COOKED`, `HIDE`) with `session_id`.
   - `recommendation_history`: Event audit records logging rank position, model version, base/final scores, and context.
   - `qualitative_feedback`: Lightweight UX, explanation, or accuracy issue reports kept separate from ML training data.

### 7.2 Migrations (Alembic)
Schema evolution is managed via an unbroken linear Alembic migration chain:
```text
<base>
  └── 001_initial_schema (Catalog, ingredients, nutrition, manifest)
        └── 002_user_personalization_schema (Users, preferences, pantry, feedback, history)
              └── 9ee7090d2edc (Adds session_id to user_feedback)
                    └── 003_qualitative_feedback_schema (Adds qualitative_feedback table) [HEAD]
```

---

## 8. Data Processing Pipeline

The data ingestion, cleaning, and linking pipeline transforms heterogeneous Indian culinary datasets into validated relational schemas:

```text
[ Raw Indian Recipe Dataset (Mendeley) ]
                 │
                 ▼
[ src/cleaning/clean_recipes.py ]
   - Strip markup, standardize unicode, lowercase strings
   - Validate mandatory fields: recipe_id, recipe_name, ingredients
                 │
                 ▼
[ src/ingredients/normalizer.py & extractor.py ]
   - Extract measures, units, states (chopped, boiled, fried)
   - Disambiguate parenthetical notes and culinary aliases
                 │
                 ▼
[ Canonical Ingredient Ontology Alignment ]
   - Match to 129 canonical entities across 285 aliases
   - Maintain linkage integrity (recipe_ingredients_linked.csv)
                 │
                 ▼
[ Nutrition Profiling Engine (src/nutrition/) ]
   - Link ingredients to Canadian Nutrient File (CNF 2026) food codes
   - Convert volumetric/colloquial units to gram mass
   - Aggregate macros per recipe and calculate per-serving values
                 │
                 ▼
[ Frozen Production Artifacts (data/processed/) ]
```

---

## 9. Dataset Description

All production data artifacts are frozen in `data/processed/` and verified with SHA-256 integrity checks:

| Dataset Artifact | Records | Columns | Description |
| :--- | :--- | :--- | :--- |
| `recipes.csv` | **6,871** | 19 | Authoritative Indian recipe master catalog |
| `ingredients.csv` | **129** | 14 | Canonical ingredient ontology registry |
| `ingredient_aliases.csv` | **285** | 7 | Curated synonym dictionary (284 validated, 1 rejected) |
| `recipe_ingredients_linked.csv` | **84,246** | 14 | Structured recipe-to-ingredient links |
| `recipe_nutrition.csv` | **6,871** | 27 | Per-recipe aggregated and per-serving nutritional profiles |
| `recipe_ingredient_nutrition.csv` | **84,246** | 29 | Granular ingredient-level nutrient calculations |
| `recipe_corpus.csv` | **6,871** | 2 | Cleaned culinary text corpus for TF-IDF matrix generation |

---

## 10. Ingredient Ontology

The ontology bridges colloquial Indian recipe text with standardized data science structures:
- **Hierarchical Resolution**:
  1. Exact canonical name match.
  2. Curated alias lookup (`ingredient_aliases.csv`).
  3. Cleaned ingredient phrase normalization.
  4. Substring matching against canonical vocabulary.
- **Variant Preservation**: The ontology explicitly differentiates distinct ingredient forms (e.g., *mustard seeds* vs. *mustard oil*) to prevent erroneous substitution.
- **Coverage Statistics**:
  - Total raw strings analyzed: **84,246**
  - Unique raw ingredient strings: **25,156**
  - Canonical entities referenced: **128 / 129** (99.2%)
  - Overall recipe ingredient mapping rate: **76.87%** (64,762 mapped records)

---

## 11. Recommendation Pipeline

Every recommendation request passes through a multi-stage deterministic pipeline:
1. **Input Parsing**: Extracts query recipe ID, available pantry items, dietary preferences, and macro targets.
2. **Constraint Engine Pre-Filtering**: Evaluates hard constraints against candidate recipes, dropping incompatible candidates before scoring.
3. **Retrieval**: Gathers candidate similarity scores using TF-IDF (or dense semantic BGE when enabled).
4. **Pillar Scoring**: Calculates ingredient match, nutrition compliance, and preference fit scores.
5. **Ranking**: Computes weighted scores through the Ranking Dispatcher (XGBoost or HybridRanker).
6. **Personalization**: Applies user context adjustments (boosts for liked recipes, penalties for disliked ingredients).
7. **Tie-Breaking**: Sorts candidates deterministically by `(-hybrid_score, -similarity_score, -ingredient_match_score, recipe_id)`.
8. **Explanation & Logging**: Constructs human-readable explanations and records recommendation events in `recommendation_history`.

---

## 12. Ingredient Matching

Implemented in `src/recommendation/ingredient_matcher.py` via `IngredientMatcher`:
- **Available Coverage**: $\text{Coverage} = \frac{|\text{Available} \cap \text{Recipe Ingredients}|}{|\text{Available}|}$
- **Missing Ingredients**: Explicitly calculates $\text{Recipe Canonical Ingredients} \setminus \text{Available}$.
- **Required Ingredients**: Evaluates whether all required items are present; penalizes candidates missing required ingredients.
- **Disliked Penalties**: Subtracts $0.20$ per disliked ingredient detected in the recipe.
- **Zero-Division Protection**: All set calculations are guarded against empty available/required inputs.

---

## 13. TF-IDF / Similarity Method

### 13.1 Lexical TF-IDF Baseline (`src/recommendation/tfidf_model.py`)
- **Vectorizer**: Scikit-Learn `TfidfVectorizer` serialized in `models/recommendation/tfidf_vectorizer.joblib`.
- **Vocabulary Size**: **17,045** unique unigram/bigram tokens.
- **Matrix**: Compressed sparse row matrix (`recipe_tfidf_matrix.npz`) of shape `(6871, 17045)`.
- **Similarity Metric**: Cosine similarity via matrix dot product:
  $$\text{sim}(u, v) = \frac{u \cdot v}{\|u\|_2 \|v\|_2}$$

### 13.2 Dense Semantic Retrieval (`src/retrieval/semantic/`)
- **Model**: `BAAI/bge-small-en-v1.5` (384-dimensional dense vectors, L2 normalized).
- **Embeddings**: `models/retrieval/semantic/recipe_embeddings.npy` (`(6871, 384)`, 10.55 MB).
- **Graceful Fallback**: If dense embeddings are missing or PyTorch errors occur, the system automatically falls back to lexical TF-IDF.

---

## 14. Nutrition Scoring

Implemented in `src/recommendation/nutrition_scorer.py` via `NutritionScorer`:
- Evaluates recipe macronutrients against user targets:
  - **Calorie Target**: $\max\left(0, 1 - \frac{|\text{actual} - \text{target}|}{\text{target}}\right)$
  - **Max Calorie Cap**: $1.0$ if $\text{actual} \le \text{max}$, else penalized linearly.
  - **Min Protein Floor**: $1.0$ if $\text{actual} \ge \text{min}$, else $\frac{\text{actual}}{\text{min}}$.
  - **Fat, Carbohydrate, and Fiber Bounds**: Clamped linear penalties for ceiling breaches.
- **Confidence Calibration**:
  - `COMPLETE`: $1.0$
  - `APPROXIMATE`: $0.85$
  - `PARTIAL`: Scaled from calculated ingredient coverage (max $0.50$).

---

## 15. Hybrid Ranking

The deterministic baseline ranker (`src/recommendation/hybrid_ranker.py`) combines the four pillars into a normalized score $\in [0.0, 1.0]$:

$$\text{Score} = w_{\text{sim}} \cdot S_{\text{sim}} + w_{\text{ing}} \cdot S_{\text{ing}} + w_{\text{nut}} \cdot S_{\text{nut}} + w_{\text{pref}} \cdot S_{\text{pref}}$$

- **Default Production Weights**:
  - Similarity ($w_{\text{sim}}$): `0.35`
  - Ingredient Match ($w_{\text{ing}}$): `0.35`
  - Nutrition ($w_{\text{nut}}$): `0.15`
  - Preferences ($w_{\text{pref}}$): `0.15`
- **Validation**: Weights must sum to $1.0 \pm 10^{-5}$.
- **Deterministic Sort Key**: `(-hybrid_score, -similarity_score, -ingredient_match_score, recipe_id)`.

---

## 16. XGBoost Ranking Model

The learning-to-rank system (`src/ranking/xgboost_ranker.py`) uses a frozen GBDT model:
- **Model Version**: `xgb_ranker_v0.1.0`
- **Artifact**: `models/ranking/xgboost_ranker.json` (98.6 KB)
- **Objective**: `rank:ndcg`
- **XGBoost Library Version**: `3.4.1`
- **Feature Space**: 30 engineered features covering retrieval scores, recipe duration, complexity, coverage ratios, and macro quantities.
- **Frozen Status**: The model was trained using weak-supervision signals for infrastructure validation. It is **frozen** and will not be retrained until genuine pilot data accumulates.
- **Mandatory Fallback**: Implemented in `src/ranking/fallback.py` (`RankingDispatcher`). Any runtime inference failure automatically falls back to `HybridRanker` without dropping user requests.

---

## 17. Personalization

Implemented in `src/personalization/scorer.py` via `PersonalizationScorer`:
- **Weight**: Configurable via `PERSONALIZATION_WEIGHT` (default `0.20`).
- **Affinities**: Compares candidate cuisine, region, and meal type against the user profile.
- **Interaction History Adjustments**:
  - Liked / Saved / Cooked: Positive affinity boost ($+0.15$ to $+0.25$).
  - Disliked / Hidden: Strong negative penalty ($-0.40$ to $-0.80$).
- **Safety Invariant**: Personalization score adjustments **cannot** bypass dietary or allergen hard constraints.

---

## 18. Hard Constraint Engine

Implemented in `src/constraints/engine.py` (Stage E):
- **Pre-Ranking Execution**: Hard filters execute prior to any scoring or ranking calculation.
- **Dietary Prohibitions**:
  - *Vegetarian*: Rejects non-vegetarian items (`vegetarian == False`).
  - *Vegan*: Rejects meat, seafood, dairy, and animal-derived products.
  - *Jain*: Strictly prohibits root vegetables (potatoes, onions, garlic, carrots, radishes, ginger, turmeric root).
  - *Satvik*: Prohibits alliums (onions, garlic, leeks, shallots, chives).
- **Allergens**: Enforces strict exclusion of specified allergens (dairy, peanuts, tree nuts, wheat/gluten, soy, sesame, mustard).
- **Zero-Result Diagnostics**: If constraints eliminate all catalog candidates, the engine returns structured diagnostic metadata detailing the exact constraint bottlenecks.

---

## 19. Recommendation Explainability

Implemented in `src/recommendation/explainability.py` via `ExplanationGenerator`:
- Generates transparent, deterministic explanation sentences using verified rule templates:
  - *Ingredient match explanation*: Identifies exact pantry ingredient overlap (e.g., `"Matches 4 of your ingredients: rice, tomato, onion, cumin"`).
  - *Dietary compliance*: Affirms compliance with requested traditions (e.g., `"Strictly honors Jain root-vegetable restrictions"`).
  - *Nutritional fit*: Details alignment with targets (e.g., `"Within 5% of your 450 kcal target with 18g protein"`).
- Prohibits hallucinated claims or non-deterministic generative text.

---

## 20. Feedback System

Implemented in `src/api/routes/user.py` and `src/personalization/service.py`:
- **Structured Interaction Types**: `LIKE`, `DISLIKE`, `SAVE`, `COOKED`, `HIDE`.
- **Database Storage**: Saved to `user_feedback` table with `session_id`, rating, and optional user notes.
- **Uniqueness Constraint**: Unique index on `(user_id, recipe_id, feedback_type)` ensures duplicate submissions update rather than corrupt interaction logs.
- **Qualitative UX Feedback**: Stored separately in `qualitative_feedback` (`issue_type`, `comments`) to prevent qualitative sentiment from contaminating structured ML ranking datasets.

---

## 21. Recommendation History

Implemented in `src/personalization/history.py`:
- Every recommendation served to an authenticated user is audited in `recommendation_history`.
- Records: `session_id`, `recipe_id`, `position`, `ranking_method` (`hybrid` or `xgboost`), `model_version`, `base_score`, `personalization_score`, `final_score`, and `context_metadata`.
- Users can inspect their history via `GET /api/v1/user/history`.
- History records form the immutable audit trail for future Stage I chronological evaluation.

---

## 22. Authentication and Authorization

Implemented in `src/personalization/security.py` and `src/api/dependencies.py`:
- **Password Hashing**: Uses **Argon2id** (`time_cost=2`, `memory_cost=65536`, `parallelism=2`).
- **Token Format**: Signed JWT access tokens using **HS256** algorithm with subject (`sub`), issued-at (`iat`), and expiration (`exp`) claims.
- **Authorization**: Endpoints require `Authorization: Bearer <token>` injected via FastAPI's `HTTPBearer`.
- **User Isolation**: All profile, pantry, history, and feedback operations query strictly against `current_user.id` resolved from the validated token.
- **Account Controls**: Users can deactivate accounts (`POST /api/v1/user/deactivate`) or permanently purge all personal data (`DELETE /api/v1/user/data`).

---

## 23. Security Controls

- **Zero Committed Secrets**: `.env` and `.env.*` files are excluded by `.gitignore` and `.dockerignore`.
- **Production Key Validation**: Startup fails if `AUTH_SECRET_KEY` is a default dev string, empty, or less than 32 characters in production.
- **CORS Protection**: Explicit allow-list (`ALLOWED_ORIGINS`). Wildcard `*` is prohibited when credentials are enabled.
- **Rate Limiting**: Sliding-window rate limiter blocks brute-force authentication and API abuse.
- **SQL Injection Prevention**: All queries use parameterized SQLAlchemy 2.0 ORM expressions.
- **Output Sanitization**: Exception handlers strip internal file paths and stack traces, returning structured JSON error payloads with correlation IDs.

---

## 24. API Endpoints

### 24.1 Health & Diagnostics
- `GET /api/v1/health`: Liveness probe (returns 200 if process is running).
- `GET /api/v1/health/ready`: Readiness probe (verifies database, model artifacts, and datasets).
- `GET /api/v1/metrics`: Prometheus-style operational metrics.

### 24.2 Authentication & Pilot Cohort
- `GET /api/v1/auth/pilot-status`: Public cohort capacity and registration status.
- `POST /api/v1/auth/register`: User registration (enforces pilot capacity and invite code).
- `POST /api/v1/auth/login`: User login (returns JWT access token).

### 24.3 User Profile & Management (Authenticated)
- `GET /api/v1/user/profile`: Profile, preferences, and pantry count.
- `PUT /api/v1/user/preferences`: Update dietary constraints and food preferences.
- `PUT /api/v1/user/nutrition-targets`: Update macro/calorie targets.
- `GET /api/v1/user/pantry`: List user pantry items.
- `POST /api/v1/user/pantry`: Add or update pantry item.
- `DELETE /api/v1/user/pantry/{item_id}`: Remove pantry item.
- `POST /api/v1/user/feedback`: Record explicit interaction feedback.
- `GET /api/v1/user/feedback`: Retrieve user feedback history.
- `POST /api/v1/user/qualitative-feedback`: Submit qualitative UX feedback.
- `GET /api/v1/user/qualitative-feedback`: Retrieve submitted qualitative feedback.
- `GET /api/v1/user/history`: Paginated recommendation event history.
- `DELETE /api/v1/user/data`: Purge all user data (with optional account deletion).
- `GET /api/v1/user/pilot-status`: Participant activity metrics.
- `POST /api/v1/user/deactivate`: Deactivate participant account.

### 24.4 Recipe Catalog
- `GET /api/v1/recipes`: Paginated search with dietary/cuisine filters.
- `GET /api/v1/recipes/{recipe_id}`: Recipe detail lookup.
- `GET /api/v1/recipes/{recipe_id}/nutrition`: Recipe nutrition breakdown.
- `GET /api/v1/recipes/{recipe_id}/similar`: Similar recipes lookup.

### 24.5 Recommendations
- `POST /api/v1/recommend`: General recommendation endpoint.
- `POST /api/v1/recommend/by-ingredients`: Pantry ingredient matching recommendation.
- `POST /api/v1/recommend/semantic`: Dense semantic retrieval recommendation (when enabled).

---

## 25. Docker Architecture

The container is built from a two-stage `Dockerfile`:
- **Builder Stage**: `python:3.12-slim`, builds dependencies and wheels.
- **Runner Stage**: `python:3.12-slim`, installs runtime libraries (`libgomp1`, `curl`).
- **Non-Root Execution**: Runs under unprivileged user `appuser` (`uid=10001`, `gid=10001`).
- **Asset Inclusions**:
  - `src/` (application source code)
  - `data/` (frozen datasets)
  - `models/` (model artifacts)
  - `frontend/` (static frontend assets)
  - `alembic/` & `alembic.ini` (migration tools)
- **Container Healthcheck**:
  ```dockerfile
  HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
      CMD curl -f http://127.0.0.1:8000/api/v1/health || exit 1
  ```
- **Entrypoint**: `python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log`

---

## 26. Azure Deployment Architecture

| Component | Azure Service | Specification / Name |
| :--- | :--- | :--- |
| **Compute** | Azure Container Apps | `kitchenpilot-api` (Consumption tier, Express environment `kitchenpilot-env`) |
| **Resource Group** | Azure Resource Group | `KitchenPilot-Production` (Region: `Malaysia West`) |
| **Active Revision** | Single Active Revision | `kitchenpilot-api--latest` (1 replica, min 1, max 2) |
| **Registry** | Azure Container Registry | `kitchenpilotregistry.azurecr.io` |
| **Identity** | User-Assigned Managed Identity | `kitchenpilot-containerapp-identity` |
| **Database** | Azure Database for PostgreSQL | Flexible Server with SSL/TLS enforcement |
| **Public FQDN** | HTTPS Ingress | `kitchenpilot-api.whitestone-ffca5e6e.malaysiawest.azurecontainerapps.io` |
| **Secret References** | Azure Container App Secrets | `secretref:auth-secret-v2`, `secretref:database-url-v2` |

---

## 27. Production Configuration

Production configuration is controlled via environment variables injected into the Azure Container App:
- `ENVIRONMENT=production`
- `DATA_BACKEND=postgres`
- `DATABASE_URL=secretref:database-url-v2`
- `AUTH_ENABLED=true`
- `AUTH_SECRET_KEY=secretref:auth-secret-v2`
- `AUTH_ALGORITHM=HS256`
- `AUTH_TOKEN_EXPIRE_MINUTES=10080` (7 days)
- `CONSTRAINT_ENGINE_ENABLED=true`
- `XGBOOST_RANKING_ENABLED=false` (HybridRanker primary; XGBoost tested and ready)
- `PERSONALIZATION_ENABLED=true`
- `PERSONALIZATION_WEIGHT=0.20`
- `FEEDBACK_ENABLED=true`
- `RECOMMENDATION_HISTORY_ENABLED=true`
- `RATE_LIMIT_ENABLED=true`
- `STRUCTURED_LOGGING=true`
- `METRICS_ENABLED=true`
- `PILOT_MODE=true`
- `PILOT_MAX_USERS=50`
- `PILOT_INVITE_CODE=""` (Open registration up to capacity limit)

---

## 28. Testing Strategy

The repository maintains an automated testing pyramid:
1. **API & Contract Tests** (`test_api.py`, `test_api_contract.py`): Route validation, status codes, and Pydantic schema serialization.
2. **Constraint Engine Tests** (`test_constraint_engine.py`): Verification of Jain, Satvik, Vegetarian, Vegan, allergen, and required ingredient constraints.
3. **Data Quality Tests** (`test_data_contracts.py`, `test_data_integrity.py`, `test_nutrition_data_quality.py`): Null checks, boundary checks, and referential integrity across 84,246 links.
4. **Database & Parity Tests** (`test_database_models.py`, `test_database_parity.py`): SQLAlchemy model definitions, foreign keys, and linear Alembic migration chain.
5. **Frontend Asset Tests** (`test_frontend.py`): Verifies required static HTML/CSS/JS files, script tag ordering, and client API contracts.
6. **Machine Learning Lifecycle** (`test_ml_lifecycle.py`, `test_xgboost_ranking.py`): Model loading, feature schema validation, NDCG/MRR metrics, and data sufficiency guards.
7. **Production Hardening** (`test_production_hardening.py`, `test_production_smoke.py`, `test_pilot_operations.py`): In-memory rate limiting, security headers, correlation IDs, 13-step end-to-end smoke workflows, and pilot capacity controls.

---

## 29. Test Results

Results from the full test run:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Python\KitchenPilot-V1
configfile: pytest.ini
collected 249 items

tests\test_api.py .................                                      [  6%]
tests\test_api_contract.py .....                                         [  8%]
tests\test_constraint_engine.py .......................                  [ 18%]
tests\test_data_contracts.py ............................                [ 29%]
tests\test_data_integrity.py ....                                        [ 30%]
tests\test_database_models.py .......                                    [ 33%]
tests\test_database_parity.py ..s                                        [ 34%]
tests\test_frontend.py ......                                            [ 37%]
tests\test_ingredient_ontology.py .........                              [ 40%]
tests\test_ml_lifecycle.py ........                                      [ 44%]
tests\test_nutrition_data_quality.py ..................                  [ 51%]
tests\test_nutrition_engine.py .....................                     [ 59%]
tests\test_personalization.py .....................                      [ 68%]
tests\test_pilot_operations.py .............                             [ 73%]
tests\test_production_hardening.py ........                              [ 76%]
tests\test_production_smoke.py .                                         [ 77%]
tests\test_recommendation_engine.py ................                     [ 83%]
tests\test_release.py ........                                           [ 86%]
tests\test_repository_abstraction.py ....                                [ 88%]
tests\test_semantic_retrieval.py .................                       [ 95%]
tests\test_xgboost_ranking.py ............                               [100%]

============ 248 passed, 1 skipped, 1 warning in 947.31s (0:15:47) ============
```

*(Note: 1 test skipped in `test_database_parity.py` when running locally without a live local PostgreSQL instance; all other 248 tests passed).*

---

## 30. Production Verification

The production deployment of commit `a35e84a` on Azure Container Apps was verified via live HTTP probes:
- **Liveness (`/api/v1/health`)**: `HTTP 200 OK` (`{"status":"ok","service":"KitchenPilot-V1","version":"1.0.0"}`)
- **Readiness (`/api/v1/health/ready`)**: `HTTP 200 OK` (all 7 critical checks `true`, including `database_connectivity: true`)
- **Anonymous Recommendation (`/api/v1/recommend/by-ingredients`)**: `HTTP 200 OK` (successfully returned top 3 Indian dishes matching test pantry items)
- **Token Boundary Check (`/api/v1/user/history`)**: `HTTP 401 Unauthorized` (correctly blocked anonymous access)
- **Deployment Gates (`scripts/deployment_gate.py`)**: All 5 release gates approved.
- **Pilot Safety Monitor (`scripts/verify_pilot_safety.py`)**: 0 constraint violations, 0 data leakage, 0 secret exposure.

---

## 31. Pilot Mode

Controlled pilot onboarding (Stage J) protects operational capacity and data integrity:
- **`PILOT_MODE` Toggle**: Master switch allowing or pausing participant registration without service downtime.
- **`PILOT_MAX_USERS`**: Hard cohort ceiling set to **50** participants. Registration endpoint returns `HTTP 403 Forbidden` once capacity is reached.
- **`PILOT_INVITE_CODE`**: Optional secret string required at registration when configured by the pilot administrator.
- **Data Invariant**: Synthetic or fabricated user interaction data is strictly prohibited.

---

## 32. Current Pilot Status

- **Software Status**: Production deployed, hardened, and verified live on Azure Container Apps.
- **Database Status**: PostgreSQL connected, schema migrated through `003_qualitative_feedback_schema`.
- **Cohort Enrollment**: **1 active verified participant**, **49 available slots** remaining out of 50.
- **Longitudinal Pilot Data Collection**: **PENDING**.
- **Stage I ML Retraining Readiness**: Correctly reports `UNMET` (requires minimum 20 users, 200 interaction events, 7 active days, 50 positive / 20 negative labels). Real-world pilot data collection will satisfy these criteria naturally during the pilot period.

---

## 33. Known Limitations

1. **Frozen Reference Data**: Nutritional values reflect Canada Nutrient File (CNF 2026) curated matches; external dynamic nutrition lookups are not performed at runtime.
2. **Deterministic Explanations**: Explanations use rule-based templates rather than generative LLMs to guarantee determinism and prevent hallucinations.
3. **No Image Recognition**: Visual identification of ingredients or dishes via photos is intentionally excluded from the V1 scope.
4. **Cold-Start Recommendations**: Recommendations for newly registered users rely on the four-pillar hybrid ranker until personal interaction feedback accumulates.

---

## 34. Future Work

1. **Pilot Phase Rollout**: Progressively expand the participant cohort through Phase 1 (Canary, 5–10 users), Phase 2 (Expanded, 10–25 users), and Phase 3 (Full Cohort, 25–50 users) in accordance with `docs/PILOT_OPERATIONS.md`.
2. **Stage I Candidate Retraining**: Execute `scripts/train_production_ranker.py` and promote model candidates only after the genuine feedback sufficiency threshold is achieved.
3. **Automated Weekly Quality Audits**: Run `scripts/audit_pilot_data_quality.py` and `scripts/generate_pilot_kpi_report.py` on a recurring schedule.
4. **Edge Deployment Options**: Package lightweight container variants for edge appliances and offline kitchen displays.

---

## 35. Final Release Information

- **Release Name**: KitchenPilot-V1 Production Release
- **Release Version**: `1.0.0`
- **Release Commit**: `a35e84a445a12723d85ab3bd32c4f583f70af401` (`a35e84a`)
- **Docker Image Tag**: `kitchenpilotregistry.azurecr.io/kitchenpilot-api:a35e84a445a12723d85ab3bd32c4f583f70af401`
- **Docker Image Digest**: `sha256:d239c51cfd87ad7ffaaa6ff68105bf14fa1f5b11160aa240061a17fd6fa17194`
- **Azure Container App**: `kitchenpilot-api` (Resource Group: `KitchenPilot-Production`, Environment: `kitchenpilot-env`)
- **Active Revision**: `kitchenpilot-api--latest`
- **License**: MIT
