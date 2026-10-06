# KitchenPilot-V1 — Backup & Recovery Runbook (Stage J)

## 1. Overview & Scope

This runbook defines disaster recovery procedures, point-in-time backup specifications, artifact integrity verification, and restoration validation for **KitchenPilot-V1**.

### Recoverable Assets
1. **Relational Database**: PostgreSQL user tables, auth credentials, user profiles, pantry items, recommendation history, and user feedback events.
2. **Authoritative Datasets**: Raw and processed recipe catalogs (`data/processed/recipes_cleaned.csv`, `data/mappings/`).
3. **Machine Learning Model Artifacts**: Active XGBoost ranker (`models/ranking/xgboost_ranker.json`), feature metadata, and model registry records (`models/ml_lifecycle/`).
4. **Semantic Vectors & Indices**: BGE semantic recipe embeddings (`data/processed/bge_embeddings.npy`) and TF-IDF matrix caches.
5. **Runtime Configurations**: Environment definitions and cryptographic salts (`.env.production`).

---

## 2. PostgreSQL Backup Procedures

### 2.1 Full Logical Backup (`pg_dump`)
Execute automated or manual logical snapshot:
```powershell
# Set timestamp and backup target
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"
$BACKUP_FILE = "backups/kitchenpilot_pg_${TIMESTAMP}.dump"

# Perform compressed custom-format pg_dump
pg_dump -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER -F c -b -v -f $BACKUP_FILE $env:POSTGRES_DB
```

### 2.2 Table-Specific Export (Feedback & History)
For lightweight audits or partial data recovery:
```powershell
pg_dump -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER -t user_feedback -t recommendation_history -F p -f "backups/feedback_snapshot_${TIMESTAMP}.sql" $env:POSTGRES_DB
```

---

## 3. Database Restoration Procedures

### 3.1 Pre-Restoration Safety Check
1. Ensure the running API instances are temporarily redirected to maintenance mode or stopped to prevent conflicting transactions.
2. Verify target database credentials and connectivity:
   ```powershell
   uv run python scripts/check_feedback_readiness.py
   ```

### 3.2 Full Restoration (`pg_restore`)
Restore snapshot into a clean target database:
```powershell
# Drop and recreate schema (or target new database)
pg_restore -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER -d $env:POSTGRES_DB --clean --if-exists -v $BACKUP_FILE
```

### 3.3 Post-Restoration Migration Verification
Ensure database schemas match the codebase version:
```powershell
uv run python scripts/init_db.py
uv run python -c "from src.db.session import check_db_connection; print('DB Healthy:', check_db_connection(2))"
```

---

## 4. Model Artifact & Data Integrity Verification

The application depends on frozen, verified artifacts. If files are corrupted or missing, restoration must follow these steps:

### 4.1 Model Artifact Integrity Check
Verify SHA-256 digests and model metadata using the ML Registry CLI:
```powershell
uv run python scripts/model_registry_cli.py validate xgb_ranker_v0.1.0
```
Expected output:
```text
[PASS] Artifact valid. Checksum verified: 8d00370fb80f81de6e889a1c6b75290063284a3964de85a2a9acc502b0d6677b
```

### 4.2 Restoring Active Model from Archive
If `models/ranking/xgboost_ranker.json` is missing or tampered with:
```powershell
Copy-Item "models/ml_lifecycle/archive/xgb_ranker_v0.1.0.json" -Destination "models/ranking/xgboost_ranker.json" -Force
```

### 4.3 Semantic Embeddings & Dataset Verification
Verify presence and row counts:
```powershell
uv run python -c "
import pandas as pd, numpy as np
df = pd.read_csv('data/processed/recipes.csv')
emb = np.load('models/retrieval/semantic/recipe_embeddings.npy')
assert len(df) == len(emb), f'Mismatch: {len(df)} recipes vs {len(emb)} embeddings'
print(f'Catalog verified: {len(df)} recipes cleanly indexed.')
"
```

---

## 5. Disaster Recovery Checklist

| Step | Action | Responsible / Tool | Status Check |
| :---: | :--- | :--- | :--- |
| **1** | Declare incident & isolate corrupted instance. | Operations Lead | API traffic routed to fallback |
| **2** | Provision clean PostgreSQL instance or verify target schema. | DBA / Platform | `psql -c "SELECT 1"` |
| **3** | Restore latest verified `.dump` file via `pg_restore`. | DBA | Clean return code 0 |
| **4** | Run schema verification and migrations via `init_db.py`. | Backend Lead | All tables present |
| **5** | Validate model artifact checksums via `model_registry_cli.py`. | ML Engineer | `VALID` status |
| **6** | Run end-to-end smoke test suite: `production_smoke_test.py`. | QA / Backend | 13/13 steps passed |
| **7** | Validate API contract: `test_api_contract.py`. | QA | 100% contract compliance |
| **8** | Verify health probes (`/health`, `/ready`). | Operations Lead | HTTP 200 OK |
| **9** | Re-enable pilot traffic and monitor logs for 30 minutes. | Team | Zero 5xx responses |
