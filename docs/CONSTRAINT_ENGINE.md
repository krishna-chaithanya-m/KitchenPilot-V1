# Stage E — Production Constraint & Ingredient Matching Engine

**Version:** 1.0.0  
**Status:** Verified & Integrated  
**System:** KitchenPilot-V1  
**Target Architectural Position:** Strictly between Candidate Retrieval (TF-IDF + Dense Semantic BGE Union) and Final Ranking (HybridRanker)

---

## 1. Architecture

The Constraint Engine executes as a deterministic, auditable gatekeeper sitting between candidate retrieval and final candidate scoring:

```text
                        User Request
                             │
                             ▼
                   ┌───────────────────┐
                   │ Query Construction│
                   └─────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
        TF-IDF Retriever              BGE Retriever
              │                             │
              └──────────────┬──────────────┘
                             ▼
                      Candidate Union
                             │
                             ▼
                 ┌────────────────────────┐
                 │   CONSTRAINT ENGINE    │
                 │                        │
                 │ Conflict Check         │
                 │ Allergen Exclusions    │
                 │ Ingredient Exclusions  │
                 │ Dietary Rules          │
                 │ Nutrition Limits       │
                 │ Pantry Availability    │
                 └───────────┬────────────┘
                             │
                      Eligible Candidates
                             │
                             ▼
                 ┌────────────────────────┐
                 │ Existing Hybrid Ranker │
                 │                        │
                 │ similarity             │
                 │ ingredient             │
                 │ nutrition              │
                 │ preference             │
                 └───────────┬────────────┘
                             │
                             ▼
                    Final Recommendations
                             │
                             ▼
                        Explanations
```

### Critical Architectural Invariant
**The ranking system is never allowed to override a hard constraint.** Hard exclusions happen strictly *before* ranking. Admissibility is binary: either a recipe passes all active hard constraints or it is eliminated. Soft preferences adjust scores only among admissible candidates.

---

## 2. Hard Constraints

A **HARD** constraint represents a strict requirement or safety boundary. Any candidate violating a hard constraint is rejected immediately.

| Constraint Type | Parameters | Violation Outcome |
| :--- | :--- | :--- |
| **Allergen Exclusion** | `excluded_allergens: ["dairy", "peanut", ...]` | Candidate rejected (`HARD REJECT`) |
| **Ingredient Exclusion** | `excluded_ingredients: ["onion", "garlic", ...]` | Candidate rejected (`HARD REJECT`) |
| **Dietary Rules** | `vegetarian=True`, `vegan=True`, `jain=True`, `satvik=True` | Candidate rejected (`HARD REJECT`) |
| **Nutrition Limits** | `min_calories`, `max_calories`, `min_protein_g`, etc. | Candidate rejected (`HARD REJECT`) |
| **Required Ingredients** | `required_ingredients: ["spinach", "paneer", ...]` | Candidate rejected if absent (`HARD REJECT`) |
| **Strict Pantry Mode** | `require_all_ingredients=True` | Candidate rejected if coverage < 1.0 (`HARD REJECT`) |

---

## 3. Soft Constraints

A **SOFT** constraint represents a user preference or optimization target. Candidates lacking these attributes are **not** rejected; instead, their relative relevance or ranking score is adjusted by the `HybridRanker`.

* **Preferred Ingredients**: `preferred_ingredients: ["ginger", "mint"]`
* **Pantry Coverage (Default Mode)**: `require_all_ingredients=False` provides a proportional score signal ($0.0 \dots 1.0$)
* **Cuisine Preference**: `cuisine: "South Indian"`
* **Meal Type Preference**: `meal_type: "Dinner"`
* **Preparation Time**: `max_prep_time_min` soft penalty

---

## 4. Informational Attributes

An **INFO** attribute is utilized strictly for human-readable explainability and UI presentation, and never alters candidate eligibility or ranking weights:
* Data confidence indicators (`nutrition_confidence`, `quality`)
* Matched/missing ingredient lists
* Specific detected allergens for user awareness

---

## 5. Ingredient Matching Strategy

Ingredient matching utilizes the Stage B canonical ontology (`src/ingredients/ontology.py` and `data/mappings/ingredients/ingredient_aliases.csv`).

### Matching Hierarchy
1. **Canonical Ingredient ID**: Exact match against canonical identifiers (`ING00001` - `ING00130`).
2. **Exact Canonical Name**: Direct match against canonical names (`cumin`, `onion`).
3. **Curated Alias Lookup**: Exact match against verified synonyms (`jeera` $\rightarrow$ `cumin`).
4. **Normalized Phrase Lookup**: Normalization through Unicode standardization, punctuation stripping, qualifier stripping, and controlled singularization (`fresh cumin seeds` $\rightarrow$ `cumin`).
5. **Safe Lexical Fallback**: Exact whole-word boundary matching without arbitrary fuzzy drift.
6. **Unresolved**: Unmatched ingredient phrase.

### Variant Preservation (No Dangerous Collapsing)
* **Chilli variants remain distinct**: `red chilli` (ING00096), `red chilli powder` (ING00098), `green chilli` (ING00065), and `kashmiri red chilli` (ING00069) are preserved as distinct canonical ingredients.
* **Dairy variants remain distinct**: `milk` (ING00073), `paneer` (ING00085), `butter` (ING00015), and `ghee` (ING00060) do not cross-collapse.

---

## 6. Dietary Rule Engine

Dietary evaluation enforces explicit deterministic logic using 3-state compliance:

### 1. Vegetarian
* Recipes marked `vegetarian=False` in catalog are rejected.
* Recipes containing known non-vegetarian keywords (e.g. `chicken`, `mutton`, `fish`, `egg`, `prawn`, `gelatin`) are rejected.

### 2. Vegan
* Rejects any recipe marked `vegetarian=False`.
* Rejects any recipe containing dairy or animal ingredients: `milk`, `ghee`, `paneer`, `butter`, `curd`, `cheese`, `cream`, `honey`, `yogurt`.

### 3. Jain Rules (Root Vegetable Prohibition)
* Rejects non-vegetarian recipes.
* Deterministically rejects recipes containing prohibited root vegetables:
  `onion`, `garlic`, `potato`, `carrot`, `radish`, `beetroot`, `ginger`, `sweet potato`, `yam`, `taro`, `colocasia`, `shallot`, `scallion`, `spring onion`, `leek`, `chives`.

### 4. Satvik Rules (Tamasic Ingredient Prohibition)
* Rejects non-vegetarian recipes.
* Deterministically rejects recipes containing `onion`, `garlic`, `shallot`, `scallion`, `spring onion`, `leek`, `mushroom`, `alcohol`, `wine`, `beer`.

---

## 7. Allergen Handling & Safety

Allergen exclusions are strictly enforced as **HARD** filters.

Supported major allergens:
* `dairy` (milk, paneer, curd, ghee, butter, cheese, cream, yogurt)
* `peanut` (peanuts, peanut oil)
* `tree_nut` (cashew, almond, walnut, pistachio, kaju, badam, pista)
* `gluten` (wheat, maida, sooji, semolina, rava, atta)
* `egg` (egg, whole egg, egg white, egg yolk)
* `soy` (soy, soy sauce, tofu)
* `mustard` (mustard, mustard seed, mustard oil)
* `sesame` (sesame, til)

**Safety Principle:** Explanations explicitly distinguish `"no known allergen match found"` from absolute `"allergen-free"` claims to avoid false safety guarantees.

---

## 8. Nutrition Boundary Rules

Nutritional boundaries are evaluated against per-serving figures from `data/processed/recipe_nutrition.csv`:
* `min_calories` / `max_calories`
* `min_protein_g` / `max_protein_g`
* `min_carbs_g` / `max_carbs_g`
* `min_fat_g` / `max_fat_g`
* `min_fiber_g` / `max_fiber_g`

### Data Quality Rules
* **No Arbitrary Tolerances**: A constraint `max_calories=500` enforces $cal \le 500.0$.
* **Zero Calorie Records**: The 292 recipes documented with `0.0` calories in Stage B remain unmodified and are evaluated objectively as `0.0`.
* **Missing Nutrition Handling**: Missing nutrition values for constrained fields are marked `UNKNOWN` and fail hard filters under safety-first policy.

---

## 9. Pantry Availability Matching

Accepts a request-level list of available ingredients:
$$\text{coverage\_ratio} = \frac{\text{matched\_recipe\_ingredients}}{\text{total\_unique\_recipe\_ingredients}}$$

* **Default Mode (`require_all_ingredients=False`)**: Generates pantry coverage metric as a soft scoring signal and explanation element.
* **Strict Hard Mode (`require_all_ingredients=True`)**: If $\text{coverage\_ratio} < 1.0$, the candidate is rejected with an explicit list of missing items.

---

## 10. Unknown-Data Behavior

* Tri-state semantics: `COMPLIANT`, `NON_COMPLIANT`, `UNKNOWN`.
* When data is missing for a requested hard exclusion or safety boundary, the system rejects rather than assuming compliance.

---

## 11. Conflict Handling

The engine pre-validates requests for logical contradictions before candidate processing:
* `vegan=True` + `required_ingredients=["paneer"]` $\rightarrow$ Conflict detected.
* `jain=True` + `required_ingredients=["onion"]` $\rightarrow$ Conflict detected.
* `excluded_allergens=["dairy"]` + `required_ingredients=["milk"]` $\rightarrow$ Conflict detected.

When a conflict is detected, the API returns `HTTP 422 Unprocessable Entity` with a descriptive message rather than silently returning an arbitrary recipe.

---

## 12. Zero-Result Handling

When no recipes in the catalog satisfy all hard constraints:
* The engine does **not** silently relax constraints.
* The API returns `count=0`, `recommendations=[]`, and `message="No recipes satisfy all specified hard constraints."`.
* Diagnostic breakdown is provided in `diagnostics` (e.g. counts rejected by dietary, ingredient exclusion, nutrition limits).

---

## 13. API Usage

The recommendation endpoint `/api/v1/recommend` accepts Stage E constraint fields alongside legacy V1 parameters:

```json
{
  "available_ingredients": ["potato", "cumin", "turmeric"],
  "dietary_constraints": {
    "vegetarian": true,
    "jain": false
  },
  "excluded_allergens": ["peanut"],
  "excluded_ingredients": ["garlic"],
  "required_ingredients": ["cumin"],
  "nutrition_constraints": {
    "max_calories": 500,
    "min_protein_g": 10
  },
  "require_all_ingredients": false,
  "top_k": 5
}
```

---

## 14. Performance Measurements

Benchmarked against the full catalog of **6,871 recipes** (measured via `scripts/evaluate_constraint_engine.py`):

| Operation | Total Latency (6,871 recipes) | Latency per Recipe |
| :--- | :--- | :--- |
| **Ingredient Resolution** | — | **0.0047 ms** per query |
| **Dietary Compliance** | **3.16 ms** | **0.0005 ms** per recipe |
| **Allergen Exclusions** | **56.64 ms** | **0.0082 ms** per recipe |
| **Nutrition Limits** | **12.15 ms** | **0.0018 ms** per recipe |
| **Full Pipeline Candidate Filtering** | **476.36 ms** | **0.0693 ms** per recipe |

Constraint filtering adds under 0.07 ms per recipe, supporting sub-second end-to-end recommendation pipelines.

---

## 15. Backward Compatibility Verification

* All 9 existing endpoints remain fully functional.
* Legacy requests without Stage E fields execute the existing V1 path unmodified.
* Full test suite: **157 passed**, 1 skipped, 0 failed.
* Release check: **9/9 passed**.
* Authoritative datasets: **0 modified**.

---

## 16. Known Limitations

1. **Self-Reported Recipe Metadata**: Dietary compliance relies on vetted ingredient listings and flags. Homemade spice blends with undeclared trace ingredients are outside catalog scope.
2. **Zero-Calorie Entries**: 292 legacy recipes retain recorded 0.0 calories and are evaluated as 0.0 kcal per serving.
3. **Transliteration Bounds**: Non-standard phonetic spellings of colloquial ingredients beyond the 1,400+ alias dictionary remain classified as `UNRESOLVED`.
