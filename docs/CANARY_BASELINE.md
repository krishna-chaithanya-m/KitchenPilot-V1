# KitchenPilot-V1 — Canary Pilot Immutable Baseline Snapshot (Stage L)

**Document ID:** `KP-CANARY-BASE-2026-L1`  
**Creation Timestamp:** `2026-10-04T18:38:00+05:30`  
**Phase:** Stage L — Canary Pilot Execution & Real-User Data Collection  
**Immutability Policy:** **FROZEN & IMMUTABLE**. This baseline must not be modified after canary pilot activation.

---

## 1. Application Baseline

| Attribute | Baseline Value | Verification / Source |
|---|---|---|
| **Application Version** | `1.0.2` | `VERSION` |
| **Git Commit Hash** | `f5f48d091701e71542acb0a74bdd98a65fe12398` | `git rev-parse HEAD` |
| **Python Runtime** | `3.14.5` (64-bit AMD64) | Active virtual environment (`.venv`) |
| **API Framework** | FastAPI `0.115.0+`, Uvicorn `0.30.0+` | `requirements.txt` |
| **Security / Auth Engine** | Argon2id (`argon2-cffi >= 23.1.0`), PyJWT (`pyjwt >= 2.8.0`) | HS256 JWT, Argon2id password hashing |
| **Validation Framework** | Pydantic V2 (`pydantic >= 2.8.0`) | Strict contract schemas |

### Core Dependency Manifest:
- `pandas`: `>=2.2,<3.0`
- `numpy`: `>=2.0,<3.0`
- `scikit-learn`: `>=1.5,<2.0`
- `fastapi`: `>=0.115.0`
- `sentence-transformers`: `>=6.1.0`
- `torch`: `>=2.2.0`
- `xgboost`: `>=3.4.0`
- `argon2-cffi`: `>=23.1.0`
- `pyjwt`: `>=2.8.0`

---

## 2. Authoritative Data Baseline

All underlying recipe datasets, nutrition profiles, and ingredient dictionaries are frozen:

| Data Artifact | Version | SHA256 Checksum | Record Count |
|---|---|---|---|
| `data/processed/recipes.csv` | `1.0.0` | `008d75ae96cc580c96d2244a73b06017fc09c36192f34a265b0c520e3a0ae64d` | 6,871 recipes |
| `data/processed/recipe_nutrition.csv` | `1.0.0` | `84a2fdb8dabb75aeb4296554110c572a198271f23bba7a06c30a1df9d4fc3ff1` | 6,871 nutrition records |
| `data/processed/recipe_ingredients_linked.csv` | `1.0.0` | `edc9ced314a1724330cef4c896b314d9f9614640ca5de39780192c69a89efb6c` | 62,000+ links |
| `data/processed/ingredients.csv` | `1.0.0` | `8d9d81a8ea9570709e4bde040d4d52bc1f3fcc4087e7dff6d60f76555f962fe8` | 1,400+ canonical ingredients |

- **Ingredient Ontology Version:** `1.0.0` (Canonical alias mapping + allergen hierarchy + Jain/Satvik classifications)
- **Data Manifest Status:** Audited and verified in Stage J / Stage K.

---

## 3. Retrieval Pipeline Baseline

Two-tier hybrid retrieval architecture producing up to 100 candidate recipes:

### 3.1 Sparse Lexical Index (TF-IDF)
- **Vector Model:** `models/recommendation/tfidf_vectorizer.joblib`  
  **SHA256:** `17b27006a1712bb8edb5c29cf4e60152d2690d4d32c5761ebc202ad722758bbd`
- **Sparse Matrix:** `models/recommendation/recipe_tfidf_matrix.npz`  
  **SHA256:** `c7ce7d50028c876fe2835453d85bc0686eb1bf8e8469652bdcf74a0a43794793`
- **Scope:** Title, cuisine, course, normalized ingredients
- **Parameters:** Sub-linear TF scaling (`sublinear_tf=True`), N-gram range `(1, 2)`
- **Candidate Pool:** Top-50 lexical candidates

### 3.2 Dense Semantic Retrieval (BGE)
- **Model:** `BAAI/bge-small-en-v1.5` (dimension 384, cosine distance)
- **Embeddings:** `models/retrieval/semantic/recipe_embeddings.npy`  
  **SHA256:** `1423c5e233a5decdd7e6b90879c7b25166d158bcbf805336f0354f04f47ca382`
- **Candidate Pool:** Top-50 semantic candidates

### 3.3 Fusion Layer
- **Merging Strategy:** Union deduplication preserving dense and sparse scores, feeding 50–100 candidates to the Hard Constraint Engine.

---

## 4. Ranking Engine Baseline

| Component | Specification | Checksum / Baseline Metric |
|---|---|---|
| **Model Identifier** | `xgb_ranker_v0.1.0` | Promoted and frozen in Stage I |
| **Model Type** | Gradient Boosted Decision Trees (`rank:pairwise` / LambdaMART) | — |
| **Model File** | `models/ranking/xgboost_ranker.json` | `8d00370fb80f81de6e889a1c6b75290063284a3964de85a2a9acc502b0d6677b` |
| **Feature Schema** | 30 Features (`v1.0.0`) | `models/ranking/feature_schema.json` |
| **Offline Baseline** | NDCG@5: `0.8841`, NDCG@10: `0.9126`, MRR@10: `0.9412` | Evaluated on frozen benchmark |

---

## 5. Constraint Engine Rules Baseline

The constraint engine executes with **strict precedence before ranking and personalization**:

```text
Candidates (50-100) → Hard Constraints (Zero Violations) → XGBoost Ranker → Personalization Layer
```

1. **Dietary Restrictions:**
   - `vegetarian`: Strict exclusion of all meat, poultry, fish, seafood.
   - `vegan`: Strict exclusion of all animal products (dairy, honey, eggs, meat).
   - `jain`: Strict exclusion of root vegetables (onion, garlic, potato, radish, carrot) + non-veg.
   - `satvik`: Strict exclusion of onion, garlic, mushroom, alcohol, stale items.
2. **Allergen Exclusions:** Zero-tolerance filtering against 8 major allergens (Milk, Peanuts, Tree Nuts, Eggs, Wheat/Gluten, Soy, Shellfish, Fish).
3. **Pantry Constraints:** Jaccard match percentage and required missing ingredients calculation.
4. **Nutrition Ceilings:** Max calorie ceiling and macro limits.
5. **Relaxation Policy:** Hard constraints are **NEVER silently relaxed**. Empty results return zero-result diagnostics with safe suggestions.

---

## 6. Personalization Baseline

- **Personalization Engine Version:** `1.0.0`
- **Personalization Weight ($\lambda$):** `0.20`
- **Signal Aggregation:**
  - Cuisine affinity (+0.10)
  - Region affinity (+0.05)
  - Meal type affinity (+0.05)
  - Disliked ingredients (-0.50 soft penalty, hard exclusion if flagged in constraints)
  - Interaction history boost (Liked / Saved recipes)
  - Negative history suppression (Disliked / Hidden recipes)
- **Constraint Boundary:** Personalization adjustments **cannot** bypass dietary or allergen filters.

---

## 7. Infrastructure & Pilot Configuration

| Setting | Baseline Configuration |
|---|---|
| **Database Engine** | SQLAlchemy 2.x ORM (`sqlite:///:memory:` in testing, PostgreSQL 15+ in production) |
| **Pilot Mode** | `PILOT_MODE=true` |
| **Pilot Max Capacity** | `PILOT_MAX_USERS=50` (Phase 1: 5–10 active participants) |
| **Invite Mechanism** | Optional/Enforced secret invite code gating registration |
| **Kill Switch** | Setting `PILOT_MODE=false` immediately blocks new enrollments non-destructively |
| **Rate Limiting** | Auth: 20 RPM, Recommend: 60 RPM, Feedback: 60 RPM, Global: 120 RPM |

---

## 8. Baseline Invariant Declaration

1. All model weights, schemas, and catalogs recorded in this snapshot are **FROZEN**.
2. No runtime model retraining, auto-promotion, or parameter modification will occur during Stage L canary operation.
3. All future Stage L data collection, daily audits, and KPI reports must compare against this immutable baseline.
