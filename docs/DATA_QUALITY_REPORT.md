# KitchenPilot — Production Data Quality Report

## Executive Summary

This report documents the empirical data quality, schema compliance, referential integrity, and coverage metrics across all production datasets in KitchenPilot (Version 0.1.0 data architecture / Application Version 1.0.2).

All metrics reported herein are computed directly from the active dataset artifacts. Zero numbers are estimated or manufactured.

---

## 1. Dataset Inventory & Integrity Summary

| Dataset Artifact | File Path | Record Count | Column Count | Schema Status | Primary Key | PK Duplicates | Orphan Records |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| **Recipes** | `data/processed/recipes.csv` | 6,871 | 26 | PASS | `recipe_id` | 0 | 0 |
| **Recipe Nutrition** | `data/processed/recipe_nutrition.csv` | 6,871 | 26 | PASS | `recipe_id` | 0 | 0 |
| **Recipe Corpus** | `data/processed/recipe_corpus.csv` | 6,871 | 3 | PASS | `recipe_id` | 0 | 0 |
| **Canonical Ingredients** | `data/processed/ingredients.csv` | 128 | 9 | PASS | `ingredient_id` | 0 | 0 |
| **Recipe-Ingredient Links**| `data/processed/recipe_ingredients_linked.csv` | 84,246 | 13 | PASS | `(recipe_id, original_ingredient)` | 0 | 0 |
| **Per-Item Nutrition** | `data/processed/recipe_ingredient_nutrition.csv`| 84,246 | 29 | PASS | `(recipe_id, original_ingredient)` | 0 | 0 |
| **Ingredient Aliases** | `data/mappings/ingredients/ingredient_aliases.csv`| 833 | 7 | PASS | `alias_id` | 0 | 0 |

---

## 2. Null & Missing Value Analysis

### 2.1 Recipes Dataset (`recipes.csv` — 6,871 rows)
* `recipe_id`: 0 nulls (100.0% populated)
* `recipe_name`: 0 nulls (100.0% populated)
* `prep_time_min`, `cook_time_min`, `total_time_min`, `servings`: 0 nulls (100.0% populated)
* `vegetarian`, `vegan`, `jain`, `satvik`: 0 nulls (100.0% populated)
* `source_id`, `source_license`: 0 nulls (100.0% populated)
* `ingredients`: 6 nulls (0.09%) — 6 recipes in raw corpus lack ingredient text.
* `region`, `contains`: 6,871 nulls (100.0%) — Unpopulated in raw source corpus; reserved for Stage G personalization and Stage E allergen tagging.
* `calories_kcal`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`: 6,871 nulls (100.0%) — Decoupled into `recipe_nutrition.csv`.

### 2.2 Recipe Nutrition Dataset (`recipe_nutrition.csv` — 6,871 rows)
* **0 nulls** across all 26 columns (100.0% complete data matrix).

### 2.3 Canonical Ingredients Dataset (`ingredients.csv` — 128 rows)
* **0 nulls** across all 9 columns (100.0% complete data matrix).

### 2.4 Recipe-Ingredient Links (`recipe_ingredients_linked.csv` — 84,246 rows)
* `recipe_id`: 0 nulls (100.0% populated)
* `original_ingredient`: 0 nulls (100.0% populated)
* `mapping_status`, `mapping_source`: 0 nulls (100.0% populated)
* `quantity`: 11,255 nulls (13.36%) — Qualitative seasonings (e.g. "Salt - to taste", "Oil - as needed") or missing in source text.
* `unit`: 33,211 nulls (39.42%) — Discrete items (e.g. "2 Onion", "3 Tomatoes", "1 green chilli").
* `preparation`: 47,732 nulls (56.66%) — Ingredients with no stated preparation method.
* `ingredient_id`: 19,530 nulls (23.18%) — Unmapped candidate items preserved in `REVIEW` status for future ontology expansion.

---

## 3. Ingredient Mapping Coverage

* **Total Raw Ingredient Records**: 84,246
* **Unique Raw Ingredient Strings**: 25,156
* **Unique Cleaned Ingredient Phrases**: 3,929
* **Canonical Ingredients in Vocabulary**: 128
* **Compiled Active Aliases**: 833

### Mapping Breakdown:
| Mapping Category | Record Count | Percentage | Provenance |
| :--- | :---: | :---: | :--- |
| **MAPPED_CANONICAL** | 43,909 | 52.12% | Exact match to Canonical Database |
| **MAPPED_VALIDATED** | 20,807 | 24.70% | Validated candidate mapping pipeline |
| **Total Mapped** | **64,716** | **76.82%** | **Production Linked** |
| **REVIEW (Unmapped)** | **19,530** | **23.18%** | Preserved for Stage C+ ontology expansion |

---

## 4. Nutrition Engine Coverage

* **Total Recipes Evaluated**: 6,871 (100.0%)
* **Nutrition Quality Distribution**:
  - `PARTIAL`: 6,801 recipes (98.98%) — Core ingredients calculated, minor spices/herbs or review items omitted.
  - `COMPLETE`: 42 recipes (0.61%) — 100% of ingredient items successfully matched and calculated.
  - `APPROXIMATE`: 28 recipes (0.41%) — Approximate density/state calibrations applied.
* **Caloric Value Distribution**:
  - Minimum: 0.0 kcal (292 recipes where ingredients are unmapped or solely zero-calorie seasoning)
  - Median: 312.4 kcal per serving
  - Mean: 384.8 kcal per serving
  - Maximum: 7,621.1 kcal (large whole-batch festival dishes)

---

## 5. Cross-Dataset Referential Integrity

All 5 core relational foreign keys verified with 100.0% pass rate:
1. `recipe_nutrition.recipe_id` -> `recipes.recipe_id`: **0 orphan records** (6,871 / 6,871 matched).
2. `recipe_ingredients_linked.recipe_id` -> `recipes.recipe_id`: **0 orphan records** (6,865 / 6,871 recipes with links).
3. `recipe_ingredients_linked.ingredient_id` -> `ingredients.ingredient_id`: **0 orphan records** (127 / 128 canonical ingredients referenced).
4. `ingredient_aliases.canonical_ingredient_id` -> `ingredients.ingredient_id`: **0 orphan records** (833 / 833 aliases linked to valid canonical ingredients).
5. `recipe_ingredient_nutrition.recipe_id` -> `recipes.recipe_id`: **0 orphan records** (84,246 / 84,246 items matched).

---

## 6. Known Limitations & Audit Findings

1. **6 Empty-Ingredient Recipes in Source Corpus**:
   - `R00306`: Pear And Walnut Salad Recipe
   - `R01413`: Spinach and Cottage Cheese Eggless Ravioli Recipe
   - `R02072`: Thai Jasmine Sticky Rice Recipe
   - `R02098`: Classic Pavakkai Stir Fry Recipe (Bitter Gourd Fry)
   - `R07894`: Urulaikizhangu Puli Thokku Recipe
   - `R08388`: Mashed Peas Recipe
   *Mitigation*: Preserved with empty string in `recipes.csv` to ensure 100% row-level fidelity with original Kaggle dataset; documented in contracts.

2. **292 Zero-Calorie Recipes**:
   - 292 recipes have 0.0 calculated total calories due to unmapped main ingredients or recipes consisting solely of qualitative zero-calorie seasonings (water, salt, curry leaves).
   *Mitigation*: Stage C/E ontology expansion will map candidate flours, vegetables, and pulses to raise calculated recipe nutrition coverage.

3. **1 Unreferenced Canonical Ingredient**:
   - `ING00023` (`cheddar cheese`) is currently unreferenced in `recipe_ingredients_linked.csv` because recipes with cheese reference `cheese` (`ING00024`) or `paneer` (`ING00085`).
