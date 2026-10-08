# KitchenPilot-V1 — Release Manifest

**Project:** KitchenPilot-V1  
**Version:** 1.0.0  
**Architecture:** Frontend → FastAPI → Recommendation/Nutrition Engines  
**Core dataset:** Mendeley Indian recipe dataset  
**Nutrition source:** CNF 2026  
**Recommendation:** TF-IDF + cosine similarity + ingredient matching + nutrition scoring + preference filtering + hybrid ranking  
**Image recognition:** Not included in V1  

---

## 1. System Overview

KitchenPilot-V1 is an offline-capable, deterministic, personalized recipe recommendation and nutrition analysis system tailored for Indian cuisine. The system provides an interactive web interface powered by a high-performance FastAPI backend, backed by frozen, audited culinary datasets and scientific nutrient profiles from the Canadian Nutrient File (CNF 2026).

---

## 2. Release Components

### 2.1 Static Frontend (`frontend/`)
- `index.html`: Hero landing page, feature highlights, and system status health indicator.
- `recipes.html`: Searchable and filterable catalog with pagination, diet tags, and cuisine filters.
- `recipe.html`: Comprehensive recipe detail view displaying instructions, ingredients, and calculated macro/micronutrient breakdown.
- `recommendations.html`: Interactive recommendation generator supporting pantry ingredient inputs, dietary constraints, and macro goals.
- `css/style.css`: Responsive, accessible custom styling.
- `js/config.js`: Dynamic API environment configuration supporting development and Azure production/pilot targets.
- `js/api.js`: Unified API client supporting configurable API base URL and reverse-proxy deployment.

### 2.2 Application Backend (`src/api/`)
- `src/api/main.py`: FastAPI application entrypoint with lifespan event handlers for pre-warmed engines, CORS middleware, and global error handlers.
- `src/api/schemas.py`: Pydantic V2 data contracts for recipe listings, detail views, recommendations, and health checks.
- `src/api/dependencies.py`: Dependency injection providers for singleton instances of the recommendation and nutrition engines.
- `src/api/routes/health.py`: Liveness (`/api/v1/health`) and readiness (`/api/v1/health/ready`) probes.
- `src/api/routes/recipes.py`: Recipe catalog pagination, individual recipe lookup, and nutrition retrieval endpoints.
- `src/api/routes/recommendations.py`: Similarity recommendations and ingredient-based hybrid recommendations.

### 2.3 Recommendation Engine (`src/recommendation/`)
- `src/recommendation/engine.py`: Orchestrator combining lexical cosine similarity, ingredient matching, dietary constraint filtering, and nutritional alignment.
- `src/recommendation/matching.py`: Jaccard ingredient matching and coverage scoring.
- `src/recommendation/scoring.py`: Multi-objective scoring combining similarity, ingredient overlap, and nutritional target compliance.
- `src/recommendation/filters.py`: Deterministic dietary filtering (Vegetarian, Vegan, Jain, Satvik, Allergen exclusions).
- `src/recommendation/ranking.py`: Calibrated hybrid ranking function.

### 2.4 Nutrition Engine (`src/nutrition/`)
- `src/nutrition/nutrition_engine.py`: Deterministic recipe nutrition calculator.
- `src/nutrition/ingredient_matcher.py`: Canonical ingredient linking to CNF 2026 food codes.
- `src/nutrition/unit_converter.py`: Safe culinary unit conversion engine with discrete item-mass calibrations.
- `src/nutrition/nutrient_calculator.py`: Energy and nutrient aggregation per recipe and per serving.

### 2.5 Frozen Data Artifacts (`data/processed/`)
- `data/processed/recipes.csv`: Master recipe catalog (6,000+ Indian culinary recipes).
- `data/processed/recipe_nutrition.csv`: Frozen per-recipe energy and macronutrient profiles.
- `data/processed/recipe_corpus.csv`: Prepared culinary corpus for TF-IDF indexing.
- `data/processed/recipe_ingredients_linked.csv`: Structured recipe-to-ingredient associations.
- `data/processed/ingredients.csv`: Normalized ingredient dictionary.

### 2.6 Trained Model Artifacts (`models/recommendation/`)
- `models/recommendation/tfidf_vectorizer.joblib`: Serialized Scikit-Learn TF-IDF vectorizer.
- `models/recommendation/recipe_tfidf_matrix.npz`: Sparse TF-IDF document-term matrix.
- `models/recommendation/recipe_index.csv`: Ordered mapping of matrix row indices to recipe IDs.

### 2.7 Verification & Test Suites (`tests/`, `scripts/`)
- `tests/test_api.py`: FastAPI endpoint regression tests.
- `tests/test_frontend.py`: Frontend asset and integration contract tests.
- `tests/test_release.py`: Release package and file integrity tests.
- `tests/test_constraint_engine.py`: Stage E deterministic constraint and dietary filter tests.
- `tests/test_xgboost_ranker.py`: Stage F learning-to-rank GBDT tests.
- `tests/test_personalization.py`: Stage G user authentication, pantry, feedback, and history tests.
- `tests/test_production_hardening.py`: Stage H correlation IDs, security headers, rate limiting, and metrics tests.
- `tests/test_ml_lifecycle.py`: Stage I data sufficiency, leakage prevention, and model registry tests.
- `scripts/release_check.py`: Pre-flight release verification script.
- `scripts/production_check.py`: Stage H production deployment readiness verification.
- `scripts/evaluate_user_feedback.py`: Genuine user feedback offline evaluation pipeline.
- `scripts/benchmark_performance.py`: Cold start and warm endpoint performance benchmarking.
- `scripts/train_production_ranker.py`: Stage I controlled offline candidate training pipeline.
- `scripts/model_registry_cli.py`: Stage I Model Registry CLI for candidate inspection, promotion, and rollback.

### 2.8 Stages D through L Extended Systems
- **Stage D (Dense Semantic Retrieval)**: `BAAI/bge-small-en-v1.5` embeddings (6,871 x 384) with deterministic fallback.
- **Stage E (Constraint Engine)**: Deterministic pre-ranking dietary, allergen, nutrition, and pantry constraints.
- **Stage F (GBDT Ranking)**: XGBoost `rank:ndcg` ranker (`xgb_ranker_v0.1.0`) with 30-feature schema.
- **Stage G (Personalization & Feedback)**: Argon2id + JWT authentication, user pantry, feedback, and audit history.
- **Stage H (Production Hardening & Observability)**: Correlation IDs (`X-Request-ID`), rate limiting, security headers, structured logging, `/metrics`, and Dockerized deployment.
- **Stage I (Controlled ML Lifecycle)**: Local Model Registry, data sufficiency gates, chronological query splitting, explicit promotion, and instant rollback.
- **Stage J (Controlled Pilot Cohort)**: Capacity limits (`PILOT_MAX_USERS`), optional invite codes, and pilot onboarding toggle.
- **Stage K (Pilot Safety Invariants)**: Continuous monitor verifying zero cross-user data leakage and hard constraint enforcement.
- **Stage L (Participant Feedback & Audit)**: Qualitative feedback separation from ranking interactions and engagement KPI reporting.

---

## 3. Operational Guarantees & Constraints
- Image recognition and visual recipe identification are not included.
- Automatic runtime model retraining is strictly prohibited; ML artifacts are frozen.
- No automatic candidate promotion; promotion requires explicit administrative command.
- Hard constraints always execute before ranking and personalization.
- Personalization adjustments can never bypass dietary or allergen hard constraints.
- All recommendation results remain deterministic and reproducible.
- **Pilot Data Status**: Software and deployment gates are fully complete and operational. Longitudinal real-world pilot data (20+ users, 200+ interaction events, 7+ days) is intentionally PENDING live pilot participant collection.
