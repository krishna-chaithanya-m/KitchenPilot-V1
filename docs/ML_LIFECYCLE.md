# KitchenPilot-V1 — Machine Learning Lifecycle Guide (Stage I)

## 1. Overview & Operating Principles

Stage I establishes a **strictly controlled offline ML lifecycle** for KitchenPilot-V1.

### Core Safety Invariants:
1. **No Online Learning**: Runtime inference requests and user feedback NEVER directly modify or retrain models.
2. **No Automatic Promotion**: Retraining produces a candidate model registered as `CANDIDATE`. Promotion to `PROMOTED` (active production) requires an explicit administrative command.
3. **Data Sufficiency Gate**: If genuine user interaction data does not satisfy conservative volume thresholds, retraining safely halts without modifying or fabricating data.
4. **Chronological Splitting & Leakage Prevention**: Future interactions are strictly barred from earlier partitions.
5. **Deterministic Constraint Priority**: Hard dietary and allergen constraints (Stage E) execute prior to ranking and cannot be overridden by XGBoost predictions.
6. **Full Recoverability**: Promoted models preserve the preceding baseline in `models/ml_lifecycle/archive/`, enabling immediate atomic rollback.

---

## 2. ML Lifecycle Flowchart

```text
Real User Feedback (Impression, Like, Save, Cooked, Dislike, Hide)
        ↓
Audit & Sufficiency Gate (`src/ml/data_quality.py`)
        ↓
[If Insufficient: Safely Exits — 0 Changes]
        ↓
Deterministic Conflict Resolution (`src/ml/labels.py`)
        ↓
Chronological Query-Grouped Temporal Split (`src/ml/temporal_split.py`)
        ↓
30-Feature Extraction (`src/ranking/features.py`)
        ↓
Candidate Model Training (`scripts/train_production_ranker.py`)
        ↓
Offline Comparative Evaluation (`src/ml/evaluation.py`)
        ↓
Acceptance Gates Check (Constraints = 0, NDCG >= Baseline)
        ↓
Registration in Local Registry (`models/ml_lifecycle/model_registry.json`)
        ↓
Explicit Administrator Promotion (`scripts/model_registry_cli.py promote`)
        ↓
Active Production Model Swapped & Previous Baseline Safely Archived
```

---

## 3. Data Sufficiency Thresholds

A candidate model cannot be trained unless all conservative thresholds are met:

| Parameter | Minimum Required | Purpose |
| :--- | :--- | :--- |
| `MIN_INTERACTIONS` | 200 | Statistical significance across events |
| `MIN_USERS` | 20 | Multi-user representation |
| `MIN_RECIPES` | 50 | Catalog breadth |
| `MIN_QUERY_GROUPS` | 30 | Query session diversity for LambdaMART |
| `MIN_POSITIVE_LABELS` | 40 | Positive relevance sample size |
| `MIN_NEGATIVE_LABELS` | 10 | Negative contrast signal |
| `MIN_DAYS_OF_DATA` | 7 days | Temporal span |

---

## 4. Graded Relevance & Conflict Resolution

### Graded Relevance Scale:
- `COOKED` $\rightarrow 3$ (Highest active engagement)
- `SAVE` / `LIKE` $\rightarrow 2$ (Positive preference)
- `IMPRESSION` $\rightarrow 1$ (Examined baseline, no explicit feedback)
- `DISLIKE` / `HIDE` $\rightarrow 0$ (Negative engagement)

### Conflict Precedence (when multiple events exist for same session + recipe):
$$\text{HIDE} > \text{DISLIKE} > \text{COOKED} > \text{SAVE} > \text{LIKE} > \text{IMPRESSION}$$
*Rationale*: Negative signals take strict precedence for user safety and trust, preventing disliked dishes from appearing.

---

## 5. Model Registry CLI Runbook

### List all registered models:
```powershell
.venv\Scripts\python.exe scripts/model_registry_cli.py list
```

### Display active production model:
```powershell
.venv\Scripts\python.exe scripts/model_registry_cli.py production
```

### Validate artifact integrity:
```powershell
.venv\Scripts\python.exe scripts/model_registry_cli.py validate xgb_ranker_v0.1.0
```

### Promote candidate model:
```powershell
.venv\Scripts\python.exe scripts/model_registry_cli.py promote xgb_ranker_v0.2.0
```

### Roll back to previous baseline:
```powershell
.venv\Scripts\python.exe scripts/model_registry_cli.py rollback
```
