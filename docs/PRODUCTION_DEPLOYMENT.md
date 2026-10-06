# KitchenPilot-V1 — Production Deployment, Operations & Architecture Guide (Stage H)

## 1. Overview & Architecture

KitchenPilot-V1 is an offline-capable, deterministic personalized Indian recipe recommendation platform.

### Pipeline Stages Overview
```
Client Request (with Correlation ID & Security Headers)
        ↓
In-Memory Rate Limiting & Validation Middleware
        ↓
Retrieval Layer (TF-IDF Baseline + Optional BAAI/bge-small-en-v1.5 Dense Semantic)
        ↓
Stage E Deterministic Constraint Engine (Dietary, Allergens, Pantry, Nutrition)
        ↓
Stage F Ranking Layer (XGBoost rank:ndcg with fallback to HybridRanker)
        ↓
Stage G Personalization Layer (User Profile, Ingredient Affinities, Recent Interactions)
        ↓
Deterministic Response & Recommendation Event Logging
```

---

## 2. Environment Configuration & Production Hardening

All runtime configuration is governed via environment variables.

| Variable | Default (Dev) | Production Requirement | Description |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | `production` | Enables production validation rules |
| `AUTH_SECRET_KEY` | `kitchenpilot-secure-dev...` | **Must be 32+ char high-entropy** | Key used to sign Argon2id/JWT tokens; rejected if default in prod |
| `ALLOWED_ORIGINS` | `localhost/127.0.0.1` | Explicit domain list | Strict CORS allowed origins. Wildcard `*` prohibited in prod |
| `DATA_BACKEND` | `csv` | `csv` or `postgres` | Data persistence backend |
| `DATABASE_URL` | `postgresql+psycopg://...` | External host URL | Must not point to localhost in production |
| `RATE_LIMIT_ENABLED` | `false` | `true` | In-memory sliding window rate limiting |
| `STRUCTURED_LOGGING`| `false` (in dev) | `true` (in prod) | Emits machine-readable JSON access logs |
| `METRICS_ENABLED` | `true` | `true` | Enables `/api/v1/metrics` observability |

---

## 3. Failure & Degradation Matrix

| Component / Subsystem | Failure Mode | System Behavior & Mitigation |
| :--- | :--- | :--- |
| **PostgreSQL Database** | Connection timeout or unreachable | Liveness (`/health`) returns 200; Readiness (`/health/ready`) returns 503. Recommendations continue in anonymous CSV mode if configured. |
| **XGBoost Ranking Model** | Missing artifact or schema | Deterministically falls back to heuristic `HybridRanker` without breaking the API request. |
| **Dense Semantic (BGE)** | Missing embeddings / PyTorch error | Returns documented 503 error; API clients use standard TF-IDF retrieval endpoints (`/recommend`). |
| **User Personalization** | Inactive user / expired JWT | Anonymous base ranking is served; hard constraints are strictly preserved. |
| **Feedback / Audit Logging** | Database write exception | Recommendation payload is served to user; logging failure is captured in error logs without dropping recommendations. |

---

## 4. Operational Runbook: Database Backup & Recovery

When running PostgreSQL (`DATA_BACKEND=postgres`):

### Backup (Logical Dump)
```bash
# Export schema and data with compression
pg_dump -U postgres -h <db_host> -d kitchenpilot -F c -b -v -f kitchenpilot_backup_$(date +%Y%m%d).dump
```

### Restore
```bash
# Restore logical dump into fresh target database
pg_restore -U postgres -h <db_host> -d kitchenpilot -v -c kitchenpilot_backup_20261004.dump
```

### Migrations & Rollbacks (Alembic)
```bash
# Apply pending schema migrations
alembic upgrade head

# Rollback single migration
alembic downgrade -1
```

---

## 5. Dockerized Deployment

### Standalone Docker Execution
```bash
# Build production image
docker build -t kitchenpilot-api:1.0.0 .

# Run container with production environment
docker run -d --name kitchenpilot-api \
  -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e AUTH_SECRET_KEY=$(openssl rand -hex 32) \
  -e ALLOWED_ORIGINS="https://kitchenpilot.example.com" \
  -e RATE_LIMIT_ENABLED=true \
  kitchenpilot-api:1.0.0
```

### Multi-Container Deployment via Docker Compose
```bash
# Start PostgreSQL and API service
docker compose up -d

# Verify health status
docker compose ps
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/health/ready
```

---

## 6. Observability & Monitoring

- **Liveness Probe**: `GET /api/v1/health`
  - Validates process responsiveness; independent of external dependencies.
- **Readiness Probe**: `GET /api/v1/health/ready`
  - Validates TF-IDF model artifacts, recipe corpus, datasets, DB connectivity, and config integrity.
- **Metrics Endpoint**: `GET /api/v1/metrics`
  - Exposes request counts, error rate, status code distribution, endpoint latency percentiles (P50, P95, P99), recommendation modes, and feedback counters.
- **Request Correlation**:
  - Outgoing responses include `X-Request-ID`.
  - JSON logs tag all events with `request_id`, client IP, status code, and latency in milliseconds.
