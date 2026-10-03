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
- `scripts/release_check.py`: Pre-flight release verification script.
- `src/validation/validate_recipe_nutrition.py`: 8-point nutrition engine validator.
- `src/validation/validate_recommendation_engine.py`: 14-point recommendation engine validator.

---

## 3. Exclusions from Version 1.0.0
- Image recognition and visual recipe identification are not included in V1.
- External user authentication and multi-tenant user accounts are not included in V1.
- Generative AI chatbot interfaces are not included in V1.
- Dynamic online retraining during inference is not included; models and datasets are frozen.
