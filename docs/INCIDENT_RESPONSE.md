# KitchenPilot-V1 — Incident Response Guide (Stage J)

## 1. Incident Classification Matrix

| Severity | Definition | Examples | Max Response Time |
| :---: | :--- | :--- | :---: |
| **SEV-1 (Critical)** | Core outage or critical safety violation. Recommendations failing for all users or dietary constraint breached. | Non-veg recipe served to vegetarian; DB crash causing 500s; auth bypass. | 15 minutes |
| **SEV-2 (High)** | Degradation of core functionality with fallback operating, or severe latency spike. | Latency P95 > 1.5s; semantic search failing (falling back to TF-IDF); DB read-only. | 45 minutes |
| **SEV-3 (Medium)** | Non-blocking service issue or partial administrative failure. | Feedback submission error for subset of users; ML registry report error. | 4 hours |
| **SEV-4 (Low)** | Minor cosmetic or documentation discrepancy. | UI styling glitch on small screen; non-critical log warning. | Next release |

---

## 2. Application Outage Playbooks

### Playbook A1: `/ready` Probe Failing (Database Unavailable)
1. **Symptoms**: `/ready` returns HTTP 503 `{"status": "degraded", "database": "disconnected"}`.
2. **Immediate Diagnostics**:
   ```powershell
   # Test raw TCP connectivity to PostgreSQL
   Test-NetConnection -ComputerName $env:POSTGRES_HOST -Port $env:POSTGRES_PORT
   ```
3. **Mitigation**:
   - Check PostgreSQL server status and restart service if stopped:
     ```powershell
     net start postgresql-x64-16
     ```
   - If PostgreSQL remains unreachable, temporarily fallback to CSV read-only backend:
     `DATA_BACKEND=csv` in `.env`, and restart API. In CSV mode, recommendations function normally; auth/feedback operations return controlled 503.

### Playbook A2: Model Artifact Load Failure
1. **Symptoms**: API logs `FileNotFoundError: models/ranking/xgb_ranker.json` or corrupted JSON during startup.
2. **Mitigation**:
   - Immediately restore the verified baseline model:
     ```powershell
     uv run python scripts/model_registry_cli.py rollback
     ```
   - Verify artifact integrity:
     ```powershell
     uv run python scripts/model_registry_cli.py validate xgb_ranker_v0.1.0
     ```
   - Restart API process.

---

## 3. Security Incident Playbooks

### Playbook S1: Token Compromise or Secret Leakage
1. **Symptoms**: Unauthorized API access detected, or secret key accidentally exposed in version control or logs.
2. **Immediate Mitigation**:
   - Generate a new cryptographically secure secret:
     ```powershell
     python -c "import secrets; print(secrets.token_urlsafe(48))"
     ```
   - Update `AUTH_SECRET_KEY` in production environment vault / `.env.production`.
   - Restart all API workers. This immediately invalidates all existing JWT access and refresh tokens.
   - Force all active pilot users to re-authenticate.

### Playbook S2: Brute Force or Credential Stuffing
1. **Symptoms**: High volume of 401s from `/api/v1/auth/login` targeting single or distributed IPs.
2. **Mitigation**:
   - Confirm in-memory rate limiting is active (`RATE_LIMIT_ENABLED=true`).
   - If single IP is identified, block at reverse proxy (Nginx / Cloudflare).
   - Temporary IP lockout:
     ```powershell
     # Review auth failure metrics
     curl http://localhost:8000/metrics | Select-String "auth"
     ```

---

## 4. Machine Learning & Safety Playbooks

### Playbook M1: Dietary / Allergen Constraint Violation (SEV-1)
1. **Condition**: A recipe with a restricted ingredient was returned to a user who specified that dietary constraint.
2. **Immediate Action**:
   - Suspend traffic or switch to pure keyword retrieval.
   - Run constraint diagnostic on the offending recipe:
     ```powershell
     uv run python -c "
     from src.constraints.engine import ConstraintEngine
     from src.data.loader import get_recipe_by_id
     recipe = get_recipe_by_id('<offending_id>')
     # Check violations
     "
     ```
   - Audit ingredient taxonomy and mappings in `data/mappings/`.
   - Update mappings, commit patch, and run `uv run pytest tests/test_constraint_engine.py`.

### Playbook M2: Ranking Regression or Candidate Quality Degradation
1. **Condition**: Production ranker displays anomalous behavior or degraded relevancy after a manual model update.
2. **Action**:
   - Execute explicit rollback (see `docs/ROLLBACK_RUNBOOK.md`):
     ```powershell
     uv run python scripts/model_registry_cli.py rollback
     ```
   - Re-verify production baseline `xgb_ranker_v0.1.0`.

---

## 5. Escalation & Post-Mortem

1. **Resolution Notice**: Inform all pilot stakeholders once service is restored.
2. **Blameless Post-Mortem**: Document root cause, timeline of events, detection delay, time to restore, and preventative action items within 48 hours.

---

## 6. Controlled Pilot Incident Playbooks (Stage K)

### Playbook P1: Recommendation Safety Issue (Hard Constraint Breach)
1. **Condition**: A recipe violating hard dietary or allergen constraints is served to a pilot participant.
2. **Immediate Action**:
   - **IMMEDIATELY PAUSE PILOT**: Set `PILOT_MODE=false` in environment and reload API workers.
   - Run safety verification: `uv run python scripts/verify_pilot_safety.py`.
   - Isolate the offending recipe ID and inspect ingredient tags in `data/processed/recipes.csv` and `data/mappings/`.
   - Prevent pilot resumption until 0 violations are re-verified.

### Playbook P2: Cross-User Data Leakage
1. **Condition**: Any indication that User A's pantry, preferences, or recommendation history was exposed to User B.
2. **Immediate Action**:
   - **IMMEDIATELY PAUSE PILOT**: Set `PILOT_MODE=false`.
   - Invalidate all existing tokens by rotating `AUTH_SECRET_KEY` and restarting API instances.
   - Audit database query logs for missing user ID filters in `PersonalizationService`.
   - Do not resume pilot until cross-user isolation test in `tests/test_pilot_operations.py` passes cleanly.

### Playbook P3: Authentication Bypass or Unauthorized Enrollment
1. **Condition**: Unauthenticated requests accessing protected endpoints, or registration occurring without valid invite code / exceeding capacity.
2. **Immediate Action**:
   - **IMMEDIATELY PAUSE PILOT**: Set `PILOT_MODE=false`.
   - Audit `users` table for unauthorized accounts. Deactivate unauthorized accounts: `UPDATE users SET is_active = false WHERE id = <target_id>;`.
   - Verify invite code validation logic in `src/api/routes/auth.py`.

### Playbook P4: Feedback Data Corruption or Fabrication
1. **Condition**: Inverted timestamps (`feedback < impression`), orphaned records, duplicate feedback bursts, or fabricated events detected.
2. **Immediate Action**:
   - **HALT EXPORTS & EVALUATIONS**: Stop running `scripts/export_interaction_dataset.py` and `scripts/evaluate_user_feedback.py`.
   - Run data quality audit: `uv run python scripts/audit_pilot_data_quality.py --json`.
   - Review client-side event emitters in `frontend/js/recommendations.js` for session ID desynchronization.
   - Do NOT delete or manufacture feedback; quarantine corrupted records and resolve client bugs before unpausing.

### Playbook P5: Database Outage
1. **Condition**: PostgreSQL connection refused or timed out during active pilot operations.
2. **Immediate Action**:
   - Follow `docs/BACKUP_RECOVERY.md`.
   - Check PostgreSQL daemon status: `net start postgresql-x64-16`.
   - If recovery requires restoring from snapshot, verify data checksums before resuming write operations.
   - Do NOT delete or drop production databases destructively.

### Playbook P6: Machine Learning Ranker Anomaly
1. **Condition**: Inexplicable ranking drops, NaNs in feature vectors, or candidate scoring crashes.
2. **Immediate Action**:
   - Rollback immediately to frozen production baseline `xgb_ranker_v0.1.0`:
     ```powershell
     uv run python scripts/model_registry_cli.py rollback
     ```
   - Verify SHA256 checksum against `models/ranking/metadata.json`.
   - Confirm feature vector dimensionality matches exact 30-feature baseline schema.

### Playbook P7: Performance Degradation & Latency SLA Breach
1. **Condition**: Recommendation latency P95 > 1,200 ms or database query latency P50 > 50 ms.
2. **Immediate Action**:
   - **FREEZE COHORT EXPANSION**: Halt any cohort expansion (remain in current phase; do not admit new participants).
   - Review KPI latency metrics: `uv run python scripts/generate_pilot_kpi_report.py`.
   - Inspect query profile: isolate whether bottleneck is semantic vector search, PostgreSQL connection pool exhaustion, or CPU throttling during XGBoost inference.
   - Optimize connection pooling or model cache before resuming cohort onboarding.

