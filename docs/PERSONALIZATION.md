# KitchenPilot-V1 — Stage G: User Personalization & Feedback

## 1. Overview & Architecture

Stage G introduces a production-oriented user personalization, persistent pantry, explicit feedback, and recommendation history logging layer to `KitchenPilot-V1`.

Crucially, **personalization operates strictly after Stage E hard constraints**. Under no circumstance can a user preference, liked recipe, or pantry overlap override an allergen exclusion, dietary restriction, or explicit nutritional boundary.

### Target Recommendation Pipeline
```text
                         User Request
                              │
                              ▼
                     Input Validation
                              │
                              ▼
                 User Context Lookup (Optional)
                (preferences, pantry, feedback)
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
        TF-IDF Retrieval                 BGE Retrieval
              │                               │
              └───────────────┬───────────────┘
                              ▼
                       Candidate Union
                              │
                              ▼
                     Stage E Constraints
                              │
                    ┌─────────┴─────────┐
                    │                   │
                 rejected             eligible
                    │                   │
                  STOP                  ▼
                              Feature Engineering
                                      │
                                      ▼
                             ┌─────────────────┐
                             │ Ranking Selector│
                             └────────┬────────┘
                                      │
                         ┌────────────┴────────────┐
                         ▼                         ▼
                  XGBoost enabled            XGBoost disabled
                         │                         │
                         ▼                         ▼
                  XGBoost Ranker             HybridRanker
                         │                         │
                         └────────────┬────────────┘
                                      ▼
                           Ranked Candidates Pool
                                      │
                                      ▼
                           Personalization Scorer
                       (Bounded Adjustment: [-0.2, +0.2])
                                      │
                                      ▼
                           Deterministic Final Sort
                                      │
                                      ▼
                           Explanations & Response
                                      │
                                      ▼
                           Audit History Logging
                        (recommendation_history table)
```

---

## 2. Authentication Architecture & Security

- **Password Hashing**: Argon2id via `argon2-cffi` (time_cost=2, memory_cost=64MB, parallelism=2, hash_len=32, salt_len=16). Passwords are never stored in plaintext, never logged, and never returned in API responses.
- **Tokens**: Stateless signed JWT access tokens (`pyjwt`) using `HS256`. Configurable via `AUTH_SECRET_KEY` and `AUTH_TOKEN_EXPIRE_MINUTES`.
- **User Ownership & Isolation**: All user-specific endpoints derive user identity directly from the verified JWT `sub` claim (`Depends(get_current_user)`). Clients cannot access or mutate another user's preferences, pantry, or history.
- **Anonymous Compatibility**: `Depends(get_optional_current_user)` returns `None` if the `Authorization` header is omitted, allowing anonymous recommendations to operate with exact baseline parity (`personalization_adjustment = 0.0`).

---

## 3. Database Schema & Models

### 3.1 `users`
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique user identifier |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL, INDEX | Normalized lowercase email address |
| `password_hash` | VARCHAR(255) | NOT NULL | Argon2id salted password hash |
| `display_name` | VARCHAR(128) | NULLABLE | Public user display name |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | Account status flag |
| `created_at` | TIMESTAMPTZ | NOT NULL | Account creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Last update timestamp |
| `last_login_at` | TIMESTAMPTZ | NULLABLE | Timestamp of most recent authentication |

### 3.2 `user_preferences`
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Preference record ID |
| `user_id` | INTEGER | UNIQUE, FK `users.id` CASCADE | One-to-one user linkage |
| `vegetarian` | BOOLEAN | NOT NULL, DEFAULT false | User vegetarian preference |
| `vegan` | BOOLEAN | NOT NULL, DEFAULT false | User vegan preference |
| `jain` | BOOLEAN | NOT NULL, DEFAULT false | User Jain preference |
| `satvik` | BOOLEAN | NOT NULL, DEFAULT false | User Satvik preference |
| `preferred_cuisines` | JSON | NOT NULL | Array of preferred cuisines |
| `preferred_regions` | JSON | NOT NULL | Array of preferred regional styles |
| `preferred_meal_types` | JSON | NOT NULL | Array of preferred meal types |
| `preferred_categories` | JSON | NOT NULL | Array of preferred categories |
| `preferred_ingredients` | JSON | NOT NULL | Array of liked ingredients |
| `disliked_ingredients` | JSON | NOT NULL | Array of disliked ingredients (soft penalty) |

### 3.3 `user_nutrition_targets`
| Column | Type | Description |
| :--- | :--- | :--- |
| `user_id` | INTEGER (PK, FK) | Linked user account |
| `target_calories`, `min_calories`, `max_calories` | FLOAT | Caloric goals and boundaries |
| `target_protein`, `min_protein`, `max_protein` | FLOAT | Protein goals and boundaries |
| `target_carbs`, `min_carbs`, `max_carbs` | FLOAT | Carbohydrate goals and boundaries |
| `target_fat`, `min_fat`, `max_fat` | FLOAT | Fat goals and boundaries |
| `target_fiber`, `min_fiber`, `max_fiber` | FLOAT | Dietary fiber goals and boundaries |

### 3.4 `user_pantry`
| Column | Type | Description |
| :--- | :--- | :--- |
| `user_id` | INTEGER (FK) | Linked user account |
| `ingredient_id` | VARCHAR(16) (FK) | Canonical ontology ID (from `ingredients.csv`), nullable |
| `ingredient_name` | VARCHAR(256) | Input ingredient name |
| `display_name` | VARCHAR(256) | Canonical display name |
| `quantity`, `unit` | FLOAT, VARCHAR(64) | Optional inventory quantity and unit |
| `status` | VARCHAR(32) | `IN_STOCK`, `LOW`, `OUT_OF_STOCK` |

### 3.5 `user_feedback`
| Column | Type | Description |
| :--- | :--- | :--- |
| `user_id` | INTEGER (FK) | Submitting user account |
| `recipe_id` | VARCHAR(16) (FK) | Evaluated recipe ID |
| `feedback_type` | VARCHAR(32) | `LIKE`, `DISLIKE`, `SAVE`, `COOKED`, `HIDE` |
| `rating` | FLOAT | Optional 1.0–5.0 star rating |
| `notes` | TEXT | Optional user comments |

### 3.6 `recommendation_history`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER (PK) | Event identifier |
| `user_id` | INTEGER (FK) | User account (NULL for anonymous) |
| `session_id` | VARCHAR(64) (INDEX) | Unique session / request identifier |
| `recipe_id` | VARCHAR(16) (FK) | Recommended recipe ID |
| `position` | INTEGER | Rank position presented to the user (1..K) |
| `ranking_method` | VARCHAR(64) | Ranker invoked (`hybrid` or `xgboost`) |
| `model_version` | VARCHAR(64) | Model artifact version (e.g. `xgb_ranker_v0.1.0`) |
| `personalization_applied` | BOOLEAN | Whether personalized adjustments were computed |
| `base_score` | FLOAT | Base rank score prior to personalization |
| `personalization_score` | FLOAT | Personalization adjustment ($\Delta$) |
| `final_score` | FLOAT | Resulting score after adjustment |
| `context_metadata` | JSON | Request query, top_k, constraints |
| `created_at` | TIMESTAMPTZ | Event timestamp |

---

## 4. Personalization Scoring Engine

### 4.1 Feature Extraction Schema (`v1.0.0`)
1. `cuisine_affinity` $\in \{0.0, 1.0\}$: Recipe cuisine matches user preferred cuisines.
2. `region_affinity` $\in \{0.0, 1.0\}$: Recipe region matches user preferred regions.
3. `meal_type_affinity` $\in \{0.0, 1.0\}$: Recipe meal type matches user preferred meal types.
4. `category_affinity` $\in \{0.0, 1.0\}$: Recipe category matches user preferred categories.
5. `pantry_overlap_ratio` $\in [0.0, 1.0]$: Available pantry ingredients matching recipe ingredients.
6. `preferred_ingredient_match_count` $\ge 0$: User preferred ingredients found in recipe.
7. `disliked_ingredient_penalty` $\in \{0.0, 1.0\}$: Recipe contains user disliked ingredient (soft penalty).
8. `past_liked` $\in \{0, 1\}$: Explicit LIKE recorded for recipe.
9. `past_saved` $\in \{0, 1\}$: Explicit SAVE recorded for recipe.
10. `past_cooked` $\in \{0, 1\}$: Explicit COOKED recorded for recipe.
11. `past_disliked` $\in \{0, 1\}$: Explicit DISLIKE recorded for recipe.
12. `past_hidden` $\in \{0, 1\}$: Explicit HIDE recorded for recipe.
13. `recently_recommended` $\in \{0, 1\}$: Repetition penalty if recommended recently.
14. `nutrition_target_alignment` $\in [0.0, 1.0]$: Normalized proximity to user target calories/protein.

### 4.2 Scoring Formula
Raw personalization score:
$$S_{raw} = \sum (\text{positive affinities}) - \sum (\text{penalties})$$
$$S_{clipped} = \max(-1.0, \min(1.0, S_{raw}))$$
$$\Delta_{pers} = \text{PERSONALIZATION\_WEIGHT} \times S_{clipped}$$
$$\text{final\_score} = \max(0.0, \text{base\_score} + \Delta_{pers})$$

With default $\text{PERSONALIZATION\_WEIGHT} = 0.20$, the adjustment is strictly bounded to $[-0.20, +0.20]$.

### 4.3 Deterministic Tie-Breaking
1. `final_score` descending
2. `base_score` descending
3. `recipe_id` ascending

---

## 5. Critical Invariants

1. **Hard Constraints Strictly Precede Personalization**:
   Stage E hard filters execute on the candidate pool prior to feature extraction and ranking. Rejected candidates are completely discarded. A recipe that contains an excluded allergen or violates dietary compliance can never be reintroduced by high personalization scores.
2. **Anonymous Request Parity**:
   When unauthenticated (`user_context = None`), `personalization_adjustment = 0.0`. Results match the deterministic Stage F baseline identically.
3. **ML Artifact Immutability**:
   No user feedback, profile edit, or pantry update modifies the frozen TF-IDF matrix, BGE embeddings, or XGBoost ranker artifacts. Retraining is an explicit offline process.

---

## 6. Offline Data Foundation for Future Training

Stage F model training used weak supervision. Stage G logs genuine recommendation impressions (`recommendation_history`) and explicit user feedback (`user_feedback`).

The utility script `scripts/export_interaction_dataset.py` joins impression events with user feedback to generate training datasets:
```powershell
.venv\Scripts\python.exe scripts/export_interaction_dataset.py --output data/training/user_interaction_events.csv
```
This produces labeled interaction data (`relevance_label`: 3=COOKED, 2=LIKE/SAVE, 0=DISLIKE/HIDE, 1=unlabeled impression) for future genuine ground-truth learning-to-rank models.
