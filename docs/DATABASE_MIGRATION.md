# Stage C — PostgreSQL Database Migration Guide

This document details the PostgreSQL 16 persistence architecture, schema definitions, migration procedures, dataset seeding, parity validation, and rollback operations for **KitchenPilot-V1**.

---

## 1. Overview & Architectural Design

Stage C introduces a production-grade relational database persistence backend (**PostgreSQL 16** with **SQLAlchemy 2.x** and **Alembic**) while preserving the existing CSV/Pandas backend as the default, fully functional fallback.

```text
                    ┌───────────────────────────┐
                    │      FastAPI Backend      │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │  Recommendation Engine    │
                    │  (TF-IDF / Hybrid Rank)   │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ BaseRecipeStore Interface │
                    └─────────────┬─────────────┘
                                  │
                   ┌──────────────┴──────────────┐
                   ▼                             ▼
        ┌─────────────────────┐       ┌───────────────────────┐
        │     RecipeStore     │       │  PostgresRecipeStore  │
        │   (CSV / In-Memory) │       │   (PostgreSQL 16)     │
        │      *DEFAULT*      │       │                       │
        └──────────┬──────────┘       └───────────┬───────────┘
                   │                              │
                   ▼                              ▼
        Authoritative CSV Data             PostgreSQL Tables
       (recipes.csv, etc.)               (Alembic 001_initial)
```

### Key Principles
1. **Behavioral Invariance**: Recommendations, similarity metrics, ranking weights, and API schemas are completely identical across backends.
2. **Zero Involuntary Disruption**: The default configuration remains `DATA_BACKEND=csv`. The system runs out-of-the-box without requiring an active PostgreSQL instance.
3. **Data Preservation**: Stage B authoritative contracts are strictly respected:
   - 6 recipes with NULL/empty ingredient strings (`R00306`, `R01413`, `R02072`, `R02098`, `R07894`, `R08388`) are preserved.
   - 292 recipes with `0.0` calories are preserved exactly without recalculation.
   - Stable canonical IDs (`Rxxxxx`, `INGxxxxx`) are preserved as primary keys.

---

## 2. Environment Configuration

Copy `.env.example` to `.env` to configure your local runtime:

```bash
# In your local root directory
cp .env.example .env
```

### Configuration Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DATA_BACKEND` | `csv` | Persistence backend: `csv` (default) or `postgres` |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/kitchenpilot` | Connection URI (supports `psycopg` v3) |
| `POSTGRES_DB` | `kitchenpilot` | Development database name |
| `POSTGRES_USER` | `postgres` | Database superuser |
| `POSTGRES_PASSWORD` | `postgres` | Database password |
| `POSTGRES_PORT` | `5432` | Host port mapped to PostgreSQL |

---

## 3. Starting the Local Development Database

A minimal Docker Compose configuration is provided for PostgreSQL 16:

```bash
# Start PostgreSQL 16 container in background
docker compose up -d postgres

# Verify container is healthy
docker compose ps
```

---

## 4. Database Migrations (Alembic)

Schema migrations are managed via Alembic and are decoupled from data ingestion.

```bash
# Run migrations up to latest revision (creates tables, indexes, and foreign keys)
alembic upgrade head

# Revert initial migration (if clean teardown is required)
alembic downgrade base

# Review generated SQL offline without connecting to a live database
alembic upgrade head --sql
```

### Database Tables Created
1. `recipes`: Core recipe catalog (6,871 records).
2. `ingredients`: Stage B canonical ingredient ontology (128 canonical items).
3. `ingredient_aliases`: Ingredient alias mapping (833 entries).
4. `recipe_ingredients`: Recipe-to-ingredient relationships (84,246 linked items).
5. `recipe_nutrition`: Recipe-level macronutrient profiles (6,871 records).
6. `recipe_ingredient_nutrition`: Per-ingredient nutrient breakdowns (84,246 items).
7. `dataset_manifest_metadata`: Provenance metadata recording import versions, row counts, SHA-256 hashes, and timestamps.

---

## 5. Dataset Seeding (CSV → PostgreSQL)

Seed the PostgreSQL database with the authoritative Stage B production datasets:

```bash
# Deterministic import (replaces existing rows safely)
python scripts/seed_database.py --mode replace

# Verify seeder runs transactionally with pre-validation against Stage B contracts
```

### Seeder Capabilities
- **Transactional Atomicity**: Seeding runs within database transactions; any integrity violation triggers an automatic rollback, leaving no partial state.
- **Contract Enforcement**: Validates every record with Stage B Pydantic schemas before insertion.
- **Batch Processing**: Streams records in batches of 5,000 for high throughput.
- **Audit Logging**: Inserts checksums and row counts into `dataset_manifest_metadata`.

---

## 6. Parity Validation

Verify 100% data parity between the authoritative CSV files and the PostgreSQL database:

```bash
python scripts/validate_database_parity.py
```

The parity validation suite checks:
1. **Row Count Parity**: Verifies all 6 tables match CSV row counts exactly.
2. **Primary Key Identity**: Verifies every single `recipe_id` and `ingredient_id` exists in PostgreSQL.
3. **Referential Integrity**: Validates foreign keys with zero orphan records.
4. **Canonical Fingerprints**: Computes deterministic SHA-256 hashes on normalized records.
5. **Special Cases**: Confirms preservation of NULL instructions and 0.0 calorie recipes.

---

## 7. Switching Backends & Instant Rollback

### Switching to PostgreSQL Backend
Set `DATA_BACKEND=postgres` in `.env` or in your environment:

```bash
# Windows PowerShell
$env:DATA_BACKEND="postgres"
python -m uvicorn src.api.main:app --port 8000

# Linux / macOS
DATA_BACKEND=postgres python -m uvicorn src.api.main:app --port 8000
```

### Instant Rollback to CSV
If PostgreSQL is unreachable, fails health checks, or requires maintenance, rollback immediately without downtime:

```bash
# Windows PowerShell
$env:DATA_BACKEND="csv"

# Linux / macOS
DATA_BACKEND=csv
```

The CSV engine loads instantly and serves all endpoints without external dependencies.

---

## 8. Expected Row Counts & Dataset Baseline

| Entity | Stage B Authoritative CSV | Expected PostgreSQL Rows |
| :--- | :--- | :--- |
| `recipes` | `data/processed/recipes.csv` | **6,871** |
| `ingredients` | `data/processed/ingredients.csv` | **128** |
| `ingredient_aliases` | `data/mappings/ingredient_aliases.csv` | **833** |
| `recipe_ingredients` | `data/processed/recipe_ingredients_linked.csv` | **84,246** |
| `recipe_nutrition` | `data/processed/recipe_nutrition.csv` | **6,871** |
| `recipe_ingredient_nutrition` | `data/processed/recipe_ingredient_nutrition.csv` | **84,246** |

---

## 9. Troubleshooting & FAQ

### Q: Why does `psycopg` work on Python 3.14 without manual compilation?
`psycopg` (v3) provides pre-built Windows binary wheels (`psycopg_binary==3.3.6`) compatible with Python 3.14. No compiler or Python downgrade is necessary.

### Q: What happens if `DATA_BACKEND=postgres` but the database is down?
`/api/v1/health/ready` returns HTTP 503 (`not_ready`) indicating database connectivity failure. The `/api/v1/health` liveness probe continues to respond with 200 OK.
