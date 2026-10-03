# KitchenPilot-V1

**Version: 1.0.0**

> Personalized, explainable, and nutrition-aware Indian recipe recommendation engine and full-stack system.

---

## 1. Project Overview

**KitchenPilot-V1** is a deterministic, offline-capable recommendation system tailored specifically for regional Indian cuisine. It combines:
1. **TF-IDF & Cosine Similarity**: Captures culinary style, flavor profiles, and regional preparation techniques across 6,871 recipes.
2. **Canonical Ingredient Matching**: Resolves thousands of raw ingredients and culinary aliases into 128 canonical categories, computing ingredient coverage and missing items.
3. **Verified Nutrition Scoring**: Integrates recipe macro- and micro-nutrient profiles calculated against Canadian Nutrient File (CNF) standards.
4. **Strict Dietary Filtering**: Enforces hard constraints for Vegetarian, Vegan, Jain, and Satvik dietary lifestyles before ranking.
5. **Deterministic Explainability**: Generates transparent, human-readable explanations for every recommendation without using external LLMs or black-box models.

---

## 2. Release Architecture

The release architecture follows a layered unidirectional flow:

```
Browser
  ↓
Static Frontend (HTML5 / Vanilla CSS3 / JavaScript ES6)
  ↓
FastAPI Backend (REST API / Uvicorn ASGI)
  ↓
Recommendation Engine (TF-IDF Similarity + Jaccard Matching + Hybrid Ranking)
  ↓
Nutrition Engine (CNF 2026 Reference Alignment + Item-Mass Calibrations)
  ↓
Processed Recipe/Nutrition Data (recipes.csv, recipe_nutrition.csv, ingredients.csv)
  ↓
TF-IDF Model Artifacts (tfidf_vectorizer.joblib, recipe_tfidf_matrix.npz, recipe_index.csv)
```

```
                  ┌──────────────────────────────────────────────┐
                  │              Static Frontend                 │
                  │   HTML5 / Vanilla CSS3 / JavaScript (ES6)   │
                  │   (Home, Catalog, Recipe Detail, Recommender)│
                  └──────────────────────┬───────────────────────┘
                                         │ Fetch HTTP / JSON
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │             FastAPI REST Backend             │
                  │   /api/v1/health       /api/v1/recipes       │
                  │   /api/v1/health/ready /api/v1/recommend     │
                  └──────────────┬───────────────────────────────┘
                                 │ In-memory Dependency Injection
                                 ▼
    ┌────────────────────────────────────────────────────────────────────────┐
    │                       KitchenPilot Core Engines                        │
    │                                                                        │
    │  ┌───────────────────────────┐         ┌────────────────────────────┐  │
    │  │   Recommendation Engine   │         │      Nutrition Engine      │  │
    │  │  - TF-IDF Vectorizer      │         │  - CNF Nutrient Alignment  │  │
    │  │  - Cosine Similarity      │         │  - Unit Sanity Layer       │  │
    │  │  - Canonical Matcher      │         │  - Density / State Rules   │  │
    │  │  - Hybrid Ranker          │         │  - Per-Serving Aggregator  │  │
    │  │  - Template Explanations  │         │  - Frozen Nutrition DB     │  │
    │  └─────────────┬─────────────┘         └─────────────┬──────────────┘  │
    └────────────────┼─────────────────────────────────────┼─────────────────┘
                     ▼                                     ▼
    ┌─────────────────────────────────┐   ┌──────────────────────────────────┐
    │     Trained Model Artifacts     │   │        Processed Datasets        │
    │  - tfidf_vectorizer.joblib      │   │  - recipes.csv                   │
    │  - recipe_tfidf_matrix.npz      │   │  - recipe_nutrition.csv          │
    │  - recipe_index.csv             │   │  - recipe_corpus.csv             │
    └─────────────────────────────────┘   └──────────────────────────────────┘
```

---

## 3. Technology Stack

- **Backend**: Python 3.14 (3.10+ supported), FastAPI, Uvicorn, Pydantic v2
- **Machine Learning & Math**: Scikit-Learn (TF-IDF, Cosine Similarity), NumPy, SciPy (Sparse CSR matrices)
- **Data Engineering**: Pandas, Python-dotenv
- **Testing**: Pytest, HTTPX (TestClient)
- **Frontend**: HTML5, Vanilla CSS3 (CSS Variables, Flexbox/Grid), Vanilla JavaScript (ES6+ Fetch API)

---

## 4. Directory Structure

```text
KitchenPilot-V1/
├── .env.example                     # Non-secret environment configuration template
├── .gitignore                       # Git exclusion rules
├── requirements.txt                 # Pinned project dependencies
├── README.md                        # Complete system documentation
├── data/
│   ├── mappings/                    # CNF ingredient and state mappings
│   ├── processed/                   # Frozen verified datasets
│   │   ├── recipes.csv              # Catalog metadata for 6,871 recipes
│   │   ├── recipe_nutrition.csv     # Verified macro/micro-nutrients
│   │   ├── recipe_corpus.csv        # Deterministic text corpus for TF-IDF
│   │   ├── recipe_ingredients_linked.csv # Canonical ingredient links
│   │   └── ingredients.csv          # Canonical ingredient catalog
│   └── raw/                         # Raw source recipe datasets
├── models/
│   └── recommendation/              # Serialized recommendation artifacts
│       ├── tfidf_vectorizer.joblib  # Fitted TF-IDF model (17,045 features)
│       ├── recipe_tfidf_matrix.npz  # Sparse CSR matrix (6871 x 17045)
│       └── recipe_index.csv         # Matrix row-to-recipe index mapping
├── src/
│   ├── api/                         # FastAPI REST application
│   │   ├── config.py                # Environment & path configuration
│   │   ├── dependencies.py          # In-memory RecipeStore & DI providers
│   │   ├── main.py                  # App entrypoint, CORS & error handlers
│   │   ├── schemas.py               # Pydantic v2 request/response schemas
│   │   └── routes/                  # Route handlers (health, recipes, recommend)
│   ├── nutrition/                   # Nutrition engine & CNF calculation
│   ├── recommendation/              # Recommendation engine & hybrid ranker
│   ├── evaluation/                  # Offline metrics evaluator
│   └── validation/                  # Validation suites
├── frontend/                        # Static web interface
│   ├── index.html                   # Home page & system introduction
│   ├── recipes.html                 # Paginated catalog browser
│   ├── recipe.html                  # Recipe details & nutrition profile
│   ├── recommendations.html         # Pantry & preference recommender
│   ├── css/style.css                # Responsive stylesheet
│   └── js/                          # Client-side controllers (api.js, etc.)
├── scripts/
│   └── build_recommendation_model.py # Automated TF-IDF model build script
└── tests/                           # Automated test suites (75 tests)
```

---

## 5. Prerequisites & Environment Setup

### Prerequisites
- Python **3.10** or higher (tested on **Python 3.14.5**)
- Git (optional, for version control)
- PowerShell, Bash, or Command Prompt

### Virtual Environment Creation
From the project root (`C:/Python/KitchenPilot-V1`):

```powershell
python -m venv .venv
```

Activate the virtual environment:
- **Windows (PowerShell)**:
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **Windows (Command Prompt)**:
  ```cmd
  .venv\Scripts\activate.bat
  ```
- **Linux / macOS**:
  ```bash
  source .venv/bin/activate
  ```

### Dependency Installation
```powershell
.venv\Scripts\pip install -r requirements.txt
```

---

## 6. Environment Configuration

Copy the example configuration to create `.env`:

```powershell
copy .env.example .env
```

Contents of `.env`:
```env
# Application Environment (development, staging, production)
ENVIRONMENT=development

# Server Network Binding
API_HOST=127.0.0.1
API_PORT=8000

# CORS Configuration (comma-separated origins)
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173,http://localhost:5500,http://127.0.0.1:5500

# Logging Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO
```

---

## 7. Model Artifact Preparation

The pre-trained model artifacts are included under `models/recommendation/`. If you ever need to rebuild the recommendation model artifacts deterministically:

```powershell
.venv\Scripts\python scripts/build_recommendation_model.py
```

This rebuilds:
- `data/processed/recipe_corpus.csv`
- `models/recommendation/tfidf_vectorizer.joblib`
- `models/recommendation/recipe_tfidf_matrix.npz`
- `models/recommendation/recipe_index.csv`

---

## 8. Running the Application

### 8.1. Start the FastAPI Backend

#### Development Mode (with auto-reload):
```powershell
.venv\Scripts\python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Production Mode (optimized, without reload):
```powershell
.venv\Scripts\python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

> **Note**: For production, uvicorn runs without `--reload` and can bind to `0.0.0.0` or behind a reverse proxy (e.g., Nginx, Caddy, or Cloudflare).

The API is accessible at:
- Service Root: `http://127.0.0.1:8000`
- Interactive Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc Documentation: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON Spec: `http://127.0.0.1:8000/openapi.json`

### 8.2. Start the Static Frontend (Local Development Testing)

In a second terminal:
```powershell
.venv\Scripts\python -m http.server 5500 --directory frontend --bind 127.0.0.1
```

> **IMPORTANT**: Python's built-in `http.server` is intended **strictly for local development testing**. It is single-threaded, lacks security features, and is **NOT** the recommended production frontend web server. For production, serve `frontend/` using an appropriate static web server, CDN, or reverse proxy (e.g., Nginx, Caddy, Cloudflare Pages, S3/CloudFront).

Open your browser to:
- **Frontend Home**: `http://127.0.0.1:5500/index.html`
- **Catalog**: `http://127.0.0.1:5500/recipes.html`
- **Recommendations**: `http://127.0.0.1:5500/recommendations.html`

---

## 9. API Reference & Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Operational health probe (`status: ok`) |
| `GET` | `/api/v1/health/ready` | Readiness check verifying model artifacts & datasets |
| `GET` | `/api/v1/recipes` | Paginated catalog search with filters (`page`, `page_size`, `cuisine`, etc.) |
| `GET` | `/api/v1/recipes/{recipe_id}` | Full recipe details, ingredients list, and embedded nutrition |
| `GET` | `/api/v1/recipes/{recipe_id}/nutrition` | Frozen CNF nutrition breakdown per serving and total |
| `GET` | `/api/v1/recipes/{recipe_id}/similar` | Top similar recipes by TF-IDF cosine distance |
| `POST`| `/api/v1/recommend` | General hybrid recommendation (recipe similarity + preferences + nutrition) |
| `POST`| `/api/v1/recommend/by-ingredients` | Pantry-based hybrid recommendation (`ingredients`, `user_preferences`, etc.) |

---

## 10. Automated Testing & Validation

### 10.1. Run Full Pytest Suite (75 Tests)
```powershell
.venv\Scripts\python -m pytest
```
Covers:
- `tests/test_nutrition_data_quality.py` (18 tests)
- `tests/test_nutrition_engine.py` (21 tests)
- `tests/test_recommendation_engine.py` (15 tests)
- `tests/test_api.py` (17 tests)
- `tests/test_frontend.py` (4 tests)

### 10.2. Run Nutrition Engine Validation
```powershell
.venv\Scripts\python src/validation/validate_recipe_nutrition.py
```
Validates: Source immutability, input integrity, ingredient alignment, CNF reference validity, per-serving nutrient math, and quality status integrity (8/8 checks).

### 10.3. Run Recommendation Engine Validation
```powershell
.venv\Scripts\python src/validation/validate_recommendation_engine.py
```
Validates: Determinism, duplicate exclusion, self-exclusion, score bounds `[0, 1]`, monotonicity, hard filters, excluded ingredients, required ingredients, empty lists, unknown ingredients, and top-k handling (14/14 checks).

---

## 11. Deployment

> **Important Deployment Notice**: KitchenPilot-V1 has **not** been deployed publicly. The deployment procedures documented below have been prepared and locally verified only. No internet-exposed instances or remote resources are active.

### A. Local Development

For interactive local development and debugging:

1. **Backend (with hot reload enabled)**:
   ```powershell
   .venv\Scripts\python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
   ```
2. **Frontend (local development server)**:
   ```powershell
   .venv\Scripts\python -m http.server 5500 --directory frontend --bind 127.0.0.1
   ```
3. Access the application in a local browser at `http://127.0.0.1:5500/index.html`.

---

### B. Production Backend

In a production environment, Uvicorn should run without `--reload` to prevent filesystem monitoring overhead and state leaks:

```powershell
.venv\Scripts\python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

- **Host Binding**: Bind to `0.0.0.0` inside containerized or reverse-proxied environments, or `127.0.0.1` when co-located with a local reverse proxy.
- **Workers**: Single-worker mode (`--workers 1`) is recommended because dataset and TF-IDF matrices are pre-warmed in-memory during application lifespan startup, minimizing memory consumption (~350 MB RAM total).
- **Process Manager**: Use `systemd`, `supervisord`, or Docker with restart policies in Linux production environments.

---

### C. Production Frontend

The static files located in `frontend/` (`index.html`, `recipes.html`, `recipe.html`, `recommendations.html`, `css/`, `js/`) do not require a build step (Node.js/npm is not required).

- Python's built-in `http.server` is intended **strictly for local development testing** and must **not** be used in production.
- For production, serve the `frontend/` directory using an enterprise static file server such as **Nginx**, **Caddy**, or an object storage bucket fronted by a CDN (e.g., **Cloudflare Pages**, **AWS S3 + CloudFront**).
- Configure appropriate cache-control headers: `Cache-Control: no-cache` for HTML files and `Cache-Control: public, max-age=31536000` for versioned static CSS/JS assets.

---

### D. Reverse Proxy Option

In production, placing FastAPI and the static frontend behind a reverse proxy (such as Nginx or Caddy) provides TLS termination, unified domain routing, and eliminates Cross-Origin Resource Sharing (CORS) concerns.

#### Nginx Configuration Example:
```nginx
server {
    listen 80;
    server_name kitchenpilot.example.com;

    # Serve static frontend
    location / {
        root /var/www/kitchenpilot/frontend;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # Proxy API requests to FastAPI backend
    location /api/v1/ {
        proxy_pass http://127.0.0.1:8000/api/v1/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

When using a reverse proxy where the API is mapped to `/api/v1`, configure the frontend API client by setting `window.KITCHENPILOT_API_BASE_URL = "/api/v1"` in `frontend/js/api.js` or via a global script tag before `api.js` loads.

---

### E. Environment Variables

All runtime configuration parameters are externalized through environment variables and loaded via `.env` (derived from `.env.example`):

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | Target environment (`development`, `staging`, `production`). In production, interactive docs (`/docs`, `/redoc`) can be conditionally toggled. |
| `API_HOST` | `127.0.0.1` | Network interface to bind the ASGI listener. |
| `API_PORT` | `8000` | Port for the ASGI listener. |
| `ALLOWED_ORIGINS` | `http://127.0.0.1:5500,...` | Comma-separated list of permitted CORS origins. Never use `*` when credentials or strict isolation are required. |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |

---

### F. Health Checks

Two dedicated probe endpoints are available for load balancers and orchestrators:

1. **Liveness Probe** (`GET /api/v1/health`):
   ```bash
   curl -s http://127.0.0.1:8000/api/v1/health
   # Returns: {"status":"ok","timestamp":"..."}
   ```
2. **Readiness Probe** (`GET /api/v1/health/ready`):
   ```bash
   curl -s http://127.0.0.1:8000/api/v1/health/ready
   # Returns: {"status":"ready","models_loaded":true,"recipes_indexed":6871,"nutrition_records_loaded":6871,"timestamp":"..."}
   ```
   If either the model artifacts or processed datasets fail to load during lifespan startup, this endpoint returns `HTTP 503 Service Unavailable`.

---

### G. Shutdown / Restart

- **Graceful Shutdown**: Send a `SIGTERM` or `SIGINT` (Ctrl+C) signal to the Uvicorn process. FastAPI's lifespan context manager will cleanly release all in-memory store references and terminate active HTTP connections.
- **Restart**:
  ```powershell
  # Stop existing process (PowerShell / Windows)
  Stop-Process -Id <PID> -Force
  # Launch fresh production process
  .venv\Scripts\python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 1
  ```

---

### H. Troubleshooting

1. **Port Conflicts (`Address already in use: 8000` / `5500`)**:
   - Check if an existing server process is running:
     ```powershell
     netstat -ano | findstr :8000
     ```
   - Terminate the lingering process or update `API_PORT` in `.env`.
2. **CORS Errors in Browser (`Cross-Origin Request Blocked`)**:
   - Verify that the URL serving the frontend (e.g. `http://127.0.0.1:5500`) is explicitly listed in `ALLOWED_ORIGINS` within `.env`.
3. **503 Service Unavailable on Startup**:
   - Ensure all model files exist under `models/recommendation/` and processed datasets exist under `data/processed/`.
   - Run `python scripts/release_check.py` to identify missing artifacts.
4. **Dataset/Model Corruption or Hash Mismatch**:
   - Verify file integrity using SHA-256 hashes against `RELEASE_MANIFEST.md`.

---

## 12. Known Limitations & Scope Boundaries

- **No Generative LLMs**: Explanations are generated deterministically using verified culinary rule templates.
- **Offline / Frozen Data**: Nutritional calculations reflect Canada Nutrient File (CNF) curated matches; external dynamic nutrition lookups are not performed at runtime.
- **Image Recognition**: Recipe photos and visual ingredient identification are out of scope for V1.
- **Offline Evaluation**: Precision@K and Recall@K are reported as `"Ground truth unavailable"` due to absence of historical user clickstream logs in V1.

---

## 13. Current Project Status

- **Stage 1–4**: Nutrition Data Quality & Pipeline Hardening — **FROZEN & VALIDATED**
- **Stage 5**: Deterministic Recommendation Engine — **VALIDATED**
- **Stage 6**: FastAPI Backend Integration — **VALIDATED (17/17 tests)**
- **Stage 7**: Vanilla Frontend Dashboard — **VALIDATED (4/4 tests)**
- **Stage 8**: Production Hardening & Deployment Preparation — **PASS (75/75 pytest passed)**
- **Stage 9**: Deployment & Release Preparation — **PASS**

