# KitchenPilot-V1 — Nutrition Engine Data Audit Report

**Date:** 2026-10-02  
**Status:** Audit Complete (Inspection-Only)  
**Target Path:** `data/mappings/nutrition_engine_data_audit.md`  

---

## Executive Summary

This report delivers a comprehensive, inspection-only audit of the datasets required for the upcoming KitchenPilot-V1 Recipe Nutrition Engine. All analyses were conducted without altering existing files, calculating nutrition values, or introducing external datasets.

### Primary Metrics Summary

| Dimension | Metric | Value | Proportion |
| :--- | :--- | :--- | :--- |
| **Recipe Ingredients** | Total rows | 84,246 | 100.00% |
| | Unique recipes (`recipe_id`) | 6,865 | — |
| | Unique original ingredient strings | 25,156 | — |
| | Unique parsed ingredient strings | 3,929 | — |
| **Recipe Linking** | Mapped recipe ingredient rows | 64,716 | 76.82% |
| | Unmapped recipe ingredient rows (`REVIEW`) | 19,530 | 23.18% |
| | Unique canonical ingredients linked | 127 | 99.22% of canonical |
| **Canonical Ingredients** | Total canonical ingredients | 128 | 100.00% |
| | Curated CNF `APPROVED` | 96 | 75.00% |
| | Curated CNF `NO_MATCH` | 23 | 17.97% |
| | Curated CNF `NEEDS_REVIEW` | 9 | 7.03% |
| **CNF 2026 Reference** | Unique food items | 5,993 | 100.00% |
| | Total nutrient rows | 565,409 | 100.00% |
| | Total measure conversions | 29,868 | 100.00% |
| | User-defined measure conversions (Type 6) | 21,207 | 71.00% of conversions |
| **Quantity Compatibility** | Mass-unit coverage | 2,452 | 2.91% of recipe rows |
| | Volume & household unit coverage | 48,583 | 57.67% of recipe rows |
| | Missing / blank unit rate | 33,211 | 39.42% of recipe rows |
| | Missing / blank quantity rate | 11,255 | 13.36% of recipe rows |
| | "To taste" qualitative rate | 4,995 | 5.93% of recipe rows |
| | Approved CNF mapping row coverage | 52,102 | 61.85% of recipe rows |
| | Direct CNF conversion feasibility | 31,866 | 37.82% of recipe rows |

---

## 1. Recipe Quantity Schema

### 1.1 Dataset Overview
* **File Location:** `data/processed/recipe_ingredients.csv`
* **Total Rows:** 84,246
* **Columns (6):** `original_ingredient`, `quantity`, `unit`, `ingredient`, `preparation`, `recipe_id`
* **Unique Recipes:** 6,865
* **Unique `original_ingredient` Strings:** 25,156
* **Unique Parsed `ingredient` Strings:** 3,929

### 1.2 Null Value Distribution
| Column Name | Data Type | Null Count | Null % | Populated Count | Populated % |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `original_ingredient` | string | 0 | 0.00% | 84,246 | 100.00% |
| `quantity` | string | 11,255 | 13.36% | 72,991 | 86.64% |
| `unit` | string | 33,211 | 39.42% | 51,035 | 60.58% |
| `ingredient` | string | 5 | 0.01% | 84,241 | 99.99% |
| `preparation` | string | 47,732 | 56.66% | 36,514 | 43.34% |
| `recipe_id` | string | 0 | 0.00% | 84,246 | 100.00% |

### 1.3 Distinct Units and Frequency Distribution
There are 23 distinct non-null unit strings present in the dataset:

| Rank | Unit String | Occurrence Count | % of All Rows | Category |
| :---: | :--- | :--- | :--- | :--- |
| — | *(Missing / Blank / NaN)* | 33,211 | 39.42% | Unitless / Count / To Taste |
| 1 | `teaspoon` | 17,419 | 20.68% | Volume (Household) |
| 2 | `cup` | 11,371 | 13.50% | Volume (Household) |
| 3 | `tablespoon` | 6,369 | 7.56% | Volume (Household) |
| 4 | `tablespoons` | 3,341 | 3.97% | Volume (Household) |
| 5 | `grams` | 2,286 | 2.71% | Mass (Metric) |
| 6 | `cloves` | 2,057 | 2.44% | Discrete Item (Count) |
| 7 | `cups` | 1,818 | 2.16% | Volume (Household) |
| 8 | `inch` | 1,737 | 2.06% | Linear Dimension (Ginger) |
| 9 | `teaspoons` | 1,601 | 1.90% | Volume (Household) |
| 10 | `sprig` | 1,601 | 1.90% | Discrete Item (Herbs) |
| 11 | `tsp` | 664 | 0.79% | Volume (Household) |
| 12 | `tbsp` | 220 | 0.26% | Volume (Household) |
| 13 | `ml` | 189 | 0.22% | Volume (Metric) |
| 14 | `kg` | 84 | 0.10% | Mass (Metric) |
| 15 | `gram` | 81 | 0.10% | Mass (Metric) |
| 16 | `liter` | 79 | 0.09% | Volume (Metric) |
| 17 | `clove` | 63 | 0.07% | Discrete Item (Count) |
| 18 | `sprigs` | 45 | 0.05% | Discrete Item (Herbs) |
| 19 | `inches` | 3 | <0.01% | Linear Dimension (Ginger) |
| 20 | `pieces` | 3 | <0.01% | Discrete Item (Count) |
| 21 | `liters` | 2 | <0.01% | Volume (Metric) |
| 22 | `kilograms` | 1 | <0.01% | Mass (Metric) |
| 23 | `bunch` | 1 | <0.01% | Discrete Item (Herbs) |

### 1.4 Quantity Numeric Parsing Analysis
Every single row in the dataset (84,246 rows) falls cleanly into three mutually exclusive categories:
1. **Direct Numeric (Float / Int):** 54,341 rows (64.50%)
   * Safely convertible to `float` directly.
   * Minimum numeric value: `1.0`
   * Maximum numeric value: `900.0` (typically grams)
2. **Fractions & Mixed Fractions:** 18,650 rows (22.14%)
   * **Simple Fractions (`X/Y`):** 17,353 rows (20.60%)
     * Examples: `1/2` (10,755), `1/4` (5,350), `3/4` (656), `1/3` (405), `1/8` (143), `2/3` (29), `1/1` (3), `1/6` (2), `3/8` (1), `1/5` (1).
     * Minimum fractional value: `1/8` (0.125), `1/12` (0.0833).
   * **Mixed Fractions (`W X/Y`):** 1,297 rows (1.54%)
     * Examples: `1 1/2` (1,042), `2 1/2` (135), `1 1/4` (65), `3 1/2` (15), `1 3/4` (14), `2 1/4` (12), `1 1/12` (3), `1 1/5` (3), `1 1/3` (3), `1 2/3` (2), `6 1/2` (1), `4 1/2` (1), `1 1/8` (1), `7/8` (1).
3. **Missing / Blank Quantities (`NaN`):** 11,255 rows (13.36%)
   * Corresponds to qualitative statements such as "Salt - to taste", "oil - as required", or "a pinch of asafoetida".

### 1.5 Unusual Quantity Strings and Edge Patterns
* **Unspaced Fraction Typos (7 rows):**
  * `11/2` (5 rows): e.g., `11/2 cups Water`, `11/2 cup Sugar`. This represents `1 1/2` (1.5 cups), but if evaluated naively as $11/2$, it evaluates to $5.5$ cups (a 267% overestimate).
  * `21/2` (1 row): e.g., `21/2 teaspoon Coriander Powder (Dhania)`. Represents `2 1/2` (2.5 tsp), but naively evaluates to $10.5$ tsp (a 320% overestimate).
  * `11/4` (1 row): e.g., `11/4 cup Buckwheat Flour (Kuttu Ka Atta)`. Represents `1 1/4` (1.25 cups), but naively evaluates to $2.75$ cups.
* **Range Expressions (2,008 rows in `original_ingredient`):**
  * The raw text contained ranges such as `6 to 8 Spinach Leaves (Palak)`, `3-4 Curry leaves`, `1 to 2 teaspoons Cumin seeds`.
  * **Parser Behavior:** The parser extracted the first integer into `quantity` (e.g. `6`, `3`, `1`) and left the remaining range clause in the `ingredient` column (e.g. `to 8 Spinach Leaves`, `-4 Curry leaves`).
  * Therefore, `quantity` contains **zero** literal hyphenated ranges.
* **Compound / Multi-Ingredient Strings:**
  * Raw strings where multiple ingredients were listed on one line: e.g., `1-1 / 2 tablespoon oil - 1/2 teaspoon asafoetida`. The parser extracted the first quantity (`1 1/2`) and unit (`tablespoon`), but left the second ingredient unparsed.
* **Qualitative Textual Quantities:**
  * In `original_ingredient`, terms like `to taste` (4,316 rows), `as required` (1,212 rows), `as needed` (301 rows), `pinch` (946 rows), `handful` (114 rows) occur frequently.
  * In the parsing step, these terms were routed into the `preparation` column, leaving `quantity = NaN` and `unit = NaN`.
  * In the `quantity` column itself, **zero textual words exist**.

---

## 2. Linked Recipe Ingredients

### 2.1 Dataset Overview
* **File Location:** `data/processed/recipe_ingredients_linked.csv`
* **Total Rows:** 84,246 (exact 1:1 row alignment with `recipe_ingredients.csv`)
* **Columns (13):** `original_ingredient`, `quantity`, `unit`, `ingredient`, `preparation`, `recipe_id`, `ingredient_id`, `canonical_ingredient`, `display_name`, `ingredient_form`, `category`, `mapping_status`, `mapping_source`
* **Unique Recipes:** 6,865

### 2.2 Mapping Status Distribution
| Mapping Status | Row Count | % of All Rows | `ingredient_id` Population | Semantic Definition |
| :--- | :--- | :--- | :--- | :--- |
| `MAPPED_CANONICAL` | 43,909 | 52.12% | 100% Populated | Directly linked to core canonical ingredient |
| `MAPPED_VALIDATED` | 20,807 | 24.70% | 100% Populated | Linked via verified candidate synonym/variant |
| `REVIEW` | 19,530 | 23.18% | 100% Null (`NaN`) | Unmapped original ingredients requiring review |
| **Total** | **84,246** | **100.00%** | **64,716 mapped / 19,530 unmapped** | |

### 2.3 Unmapped Ingredient Characteristics
* **Unique Unmapped `original_ingredient` Strings:** 11,733
* **Unique Unmapped `ingredient` (Parsed) Strings:** 3,474
* All 19,530 `REVIEW` rows have `ingredient_id = NaN`, `canonical_ingredient = NaN`, `display_name = NaN`, `ingredient_form = NaN`, `category = NaN`.
* No `REVIEW` row possesses an `ingredient_id`.
* No `MAPPED_*` row lacks an `ingredient_id`.

### 2.4 Integrity and Consistency
1. **Quantity and Unit Preservation:**
   * Rows are in identical order to `recipe_ingredients.csv`.
   * Differences in `quantity`: **0**
   * Differences in `unit`: **0**
   * Differences in `original_ingredient`: **0**
2. **Deterministic Mapping (No 1-to-Many Conflicts):**
   * Every distinct `original_ingredient` string maps to at most **one** canonical `ingredient_id` (0 instances of multi-mapping ambiguity).
   * Every distinct parsed `ingredient` string maps to at most **one** canonical `ingredient_id`.
3. **Canonical ID Representation:**
   * **127** unique canonical IDs appear across the 64,716 mapped rows.
   * `ING00023` (`chaat masala`, `ingredient_form: default`) has 0 occurrences in `recipe_ingredients_linked.csv` because all 232 recipes specifying chaat masala were mapped to `ING00024` (`chaat masala`, `ingredient_form: powder`).

---

## 3. Canonical Ingredient Data

### 3.1 Dataset Overview
* **File Location:** `data/processed/ingredients.csv`
* **Total Canonical Ingredients:** 128
* **Columns (9):** `ingredient_id`, `canonical_name`, `display_name`, `ingredient_form`, `category`, `recipe_occurrence_count`, `candidate_variant_count`, `source`, `mapping_status`
* **Duplicate Ingredient IDs:** 0 (strictly unique `ING00001` through `ING00128`)
* **Duplicate Canonical Names:** 24 rows sharing names with another record across distinct forms (17 unique names appear in multiple forms).

### 3.2 Category and Form Breakdown
* **Categories (24):** Spice (31), Vegetable (18), Dairy (11), Herb (8), Fruit (8), Other (6), Oil (6), Nut (5), Pulse (5), Sweetener (5), Baking (4), Condiment (4), Grain (3), Seed (2), Flour (2), Meat (2), Paste (1), Root (1), Egg (1), Dried Fruit (1), Seasoning (1), Soy (1), Flavoring (1), Liquid (1).
* **Ingredient Forms (23):** Default (83), Powder (12), Seed (7), Fresh (4), Paste (2), Flour (2), Oil (2), Desiccated (1), Stick (1), Kabuli (1), Pod (1), Whole (1), Milk (1), Leaf (1), Hung (1), Dried (1), Flakes (1), Basmati (1), Strand (1), Caster (1), Puree (1), White (1), Active Dry (1).

### 3.3 Multi-Form Canonical Ingredients
Seventeen canonical ingredients have multiple physical forms defined:
1. `coconut` (4 forms: default, desiccated, milk, oil)
2. `coriander` (3 forms: default, powder, seed)
3. `cumin` (3 forms: default, powder, seed)
4. `mustard` (3 forms: default, oil, seed)
5. `red chilli` (3 forms: dried, flakes, powder)
6. `rice` (3 forms: default, basmati, flour)
7. `black pepper` (2 forms: default, powder)
8. `cardamom` (2 forms: default, pod)
9. `chaat masala` (2 forms: default, powder)
10. `cinnamon` (2 forms: default, stick)
11. `curd` (2 forms: default, hung)
12. `fennel` (2 forms: default, seed)
13. `fenugreek leaves` (2 forms: default, fresh)
14. `sesame` (2 forms: default, seed)
15. `sugar` (2 forms: default, caster)
16. `tamarind` (2 forms: default, paste)
17. `tomato` (2 forms: default, puree)

### 3.4 Cross-Check Against Curated CNF Mappings
* **File Location:** `data/mappings/cnf_ingredient_mapping_curated.csv`
* **Total Rows:** 128 (100% 1-to-1 coverage of `ingredients.csv`, zero discrepancies)
* **Curated Decisions:**
  * **`APPROVED`:** 96 (75.00%)
  * **`NO_MATCH`:** 23 (17.97%)
  * **`NEEDS_REVIEW`:** 9 (7.03%)
* **Food Code Integrity:**
  * `APPROVED`: 96/96 have valid CNF food codes; 0 missing; 0 invalid.
  * `NEEDS_REVIEW`: 8 have valid CNF food codes; 1 is intentionally blank (`ING00026` generic cheese); 0 invalid.
  * `NO_MATCH`: 23/23 have blank CNF food codes; 0 invalid.
* **Canonical Ingredients with No Usable CNF Mapping:** 24 (23 `NO_MATCH` + 1 unmapped `NEEDS_REVIEW`).

---

## 4. CNF 2026 Nutrition Schema

### 4.1 Dataset Overview
* **File Location:** `data/processed/cnf_2026_nutrition.csv`
* **Total Rows:** 565,409
* **Columns (32):**
  * *Food attributes:* `source`, `source_reference`, `source_food_id`, `food_name`, `food_description`, `food_form`, `food_name_fr`, `alternate_names_en`, `alternate_names_fr`, `scientific_name`, `food_source_code`, `food_source_description`, `source_usda_ndb_code`, `source_cnf_food_group_code`, `source_food_last_updated_date`
  * *Nutrient attributes:* `nutrient_id`, `source_nutrient_id`, `nutrient_name`, `nutrient_name_fr`, `normalized_nutrient_name`, `nutrient_symbol`, `nutrient_tagname`, `nutrient_value`, `nutrient_unit`, `nutrient_decimals`, `standard_error`, `observations`, `nutrient_source_code`, `nutrient_source_description`, `source_date`, `basis`, `license`

### 4.2 Data Integrity and Metrics
* **Unique CNF Food Codes (`source_food_id`):** 5,993
* **Unique Nutrient IDs:** 152
* **Unique Nutrient Names:** 152
* **Duplicate `(source_food_id, nutrient_id)` Pairs:** 0 (strictly unique)
* **Missing `nutrient_value`:** 0
* **Negative `nutrient_value`:** 0
* **Nutrient Basis:** `per_100g_edible_portion` (100% uniform across all 565,409 rows)
* **Units:** `Gram`, `kCal`, `kJ`, `Milligram`, `Microgram`, `NE`, `RE`, `IU`, `mcg_DFE`, `mg_GAE`, `Ratio`

### 4.3 Core Nutrients Relevant to KitchenPilot
Our normalization pipeline explicitly standardizes the core nutritional profile via the following `nutrient_id` mapping:

| Target Nutrient | CNF Nutrient ID | CNF Nutrient Name | Normalized Field | Unit |
| :--- | :---: | :--- | :--- | :---: |
| **Protein** | `203` | Protein | `protein_g` | Gram |
| **Fat (total lipids)** | `204` | Fat (total lipids) | `fat_g` | Gram |
| **Carbohydrate** | `205` | Carbohydrate, total (by difference) | `carbs_g` | Gram |
| **Energy (Calories)** | `208` | Energy (kilocalories) | `energy_kcal` | kCal |
| **Energy (Joules)** | `268` | Energy (kilojoules) | `energy_kj` | kJ |
| **Sugars** | `269` | Sugars, total | `sugar_g` | Gram |
| **Fiber** | `291` | Fibre, total dietary | `fiber_g` | Gram |
| **Sodium** | `307` | Sodium, Na | `sodium_mg` | Milligram |

### 4.4 Additional Available Micronutrients
The schema also stores complete profiles for:
* Fatty acids: Saturated (`fatty_acids_saturated_total_606`), Monounsaturated (`645`), Polyunsaturated (`646`), Cholesterol (`601`).
* Minerals: Calcium (`301`), Iron (`303`), Potassium (`306`), Magnesium (`304`), Phosphorus (`305`), Zinc (`309`).
* Vitamins: Vitamin C (`401`), Vitamin A (`318`, `319`, `806`), Vitamin D (`324`, `811`), Folate (`417`, `431`), Vitamin B12 (`418`).

---

## 5. CNF Measure Conversion Data

### 5.1 Dataset Schema & Architecture
* **Directory:** `data/raw/nutrition/cnf_2026/`
* **Key Files:**
  * `measure_weight_conversion.csv` (29,868 rows): `Food_Code`, `Measure_Type_Code`, `Measure_Code`, `Measure_Weight_Conversion`, `Measure_Weight_Conversion_Last_Updated_Date`
  * `measure_name.csv` (1,497 rows): `Measure_Code`, `Measure_Description_and_Unit_EN`, `Measure_Description_and_Unit_FR`
  * `measure_type.csv` (3 rows):
    * `3`: Refuse (inedible portion / tare, conversion value = 0)
    * `6`: User-defined (standard serving and household measures)
    * `9`: Yield (cooking yield factor)
  * `food_name.csv` (5,993 rows)

### 5.2 Measure Conversion Mechanics
1. **Weight Unit:** `Measure_Weight_Conversion` is strictly expressed in **grams (g)**.
2. **Food Specificity:** Every measure conversion is specific to a single `Food_Code`.
3. **Representation of Standard Household Units:**
   * **1 cup:** Represented primarily as `250 ml` (Measure_Code `415`), or as prepared volume descriptions such as `250 ml chopped or diced` (Measure_Code `1032`) or `250 ml slices` (Measure_Code `979`).
   * **1 tablespoon:** Represented as `15 ml` (Measure_Code `385`, `301`, etc.).
   * **1 teaspoon:** Represented as `5 ml` (Measure_Code `439`).
   * **Count / Discrete Units:** Represented as food-specific items, such as `1 clove` (Measure_Code `482` for garlic), `1 medium whole (6.6cm dia)` (Measure_Code `1299` for tomato), `1 large` (Measure_Code `139` for onion), or `1 potato (6.3cm dia)` (Measure_Code `218`).

### 5.3 Measure Weights for Common Foods
The table below illustrates why generic density assumptions are invalid:

| Food Name | CNF Food Code | Measure Name | Weight (g) | Effective Density / Mass |
| :--- | :---: | :--- | :---: | :--- |
| **Rice (white, long-grain, dry)** | `4471` | 250 ml (1 cup) | 195.48 g | 0.782 g/ml |
| **Moong Dal (mature seeds, dry)** | `3362` | 250 ml (1 cup) | 154.27 g | 0.617 g/ml |
| **Toor Dal (red gram, dry)** | `3381` | 250 ml (1 cup) | 194.42 g | 0.778 g/ml |
| **Milk (fluid, 2% M.F.)** | `116` | 250 ml (1 cup) | 264.16 g | 1.057 g/ml |
| **Tomato Puree (canned)** | `6580` | 250 ml (1 cup) | 264.16 g | 1.057 g/ml |
| **Onion (raw, chopped)** | `2401` | 250 ml chopped (1 cup) | 169.06 g | 0.676 g/ml |
| | | 1 large whole | 150.00 g | 150 g/item |
| **Tomato (red, ripe, raw)** | `2460` | 250 ml chopped (1 cup) | 190.19 g | 0.761 g/ml |
| | | 1 medium whole (6.6cm) | 123.00 g | 123 g/item |
| | | 1 cherry tomato | 17.00 g | 17 g/item |
| **Potato (raw, flesh & skin)** | `2505` | 250 ml diced (1 cup) | 158.50 g | 0.634 g/ml |
| | | 1 medium potato | 213.00 g | 213 g/item |
| **Sunflower Oil** | `7191` | 15 ml (1 tbsp) | 13.82 g | 0.921 g/ml |
| | | 5 ml (1 tsp) | 4.61 g | 0.921 g/ml |
| **Cumin Seed** | `182` | 15 ml (1 tbsp) | 6.08 g | 0.405 g/ml |
| | | 5 ml (1 tsp) | 2.14 g | 0.429 g/ml |
| **Turmeric (ground)** | `211` | 15 ml (1 tbsp) | 6.89 g | 0.459 g/ml |
| | | 5 ml (1 tsp) | 2.25 g | 0.449 g/ml |
| **Garlic (raw)** | `2394` | 1 clove | 3.00 g | 3 g/clove |
| | | 1 bulb | 24.00 g | 24 g/bulb |
| **Ginger Root (raw)** | `2091` | 1 slice (0.3cm x 2.5cm) | 2.20 g | 2.2 g/slice |
| | | 250 ml slices | 101.44 g | 0.406 g/ml |

### 5.4 Safety of Generic Conversions
* **Finding:** Across all 2,215 foods in CNF with a `250 ml` measure, the conversion weight ranges from **3.38 g** (light puffed cereals) to **426.90 g** (heavy syrups), with a mean of **194.02 g** and standard deviation of **75.81 g**.
* Across all 471 foods with a `15 ml` (tablespoon) measure, weights range from **0.20 g** to **33.78 g** (mean: **12.58 g**).
* **Conclusion:** Applying a blanket assumption such as $1\text{ cup} = 250\text{ g}$ or $1\text{ tsp} = 5\text{ g}$ would introduce errors exceeding $300\%$ on bulk spices and dried legumes. All volume conversions must use food-specific CNF density data.

---

## 6. Quantity-to-CNF Compatibility

Using the linked recipe ingredient dataset (84,246 rows) cross-referenced with the curated CNF mappings (128 canonical ingredients):

### 6.1 Recipe Ingredient Distribution
| Category | Row Count | % of All Rows (N=84,246) | % of Mapped Rows (N=64,716) |
| :--- | :--- | :--- | :--- |
| **Direct Mass Units** (`g`, `kg`) | 2,452 | 2.91% | 3.79% |
| **Volume & Household Units** (`cup`, `tbsp`, `tsp`, `ml`, `l`, `clove`, `sprig`, `inch`) | 48,583 | 57.67% | 75.07% |
| **Missing / Blank Units** (Unitless item counts, to taste, oil as needed) | 33,211 | 39.42% | 21.14% |
| **Missing / Blank Quantity** (`NaN`) | 11,255 | 13.36% | 14.65% |
| **Qualitative "To Taste"** | 4,995 | 5.93% | 7.64% |

### 6.2 Curation Status Coverage Across Recipe Rows
| Canonical Curation Status | Recipe Rows (N=84,246) | % of All Rows | % of Mapped Rows (N=64,716) | Canonical Count (N=128) |
| :--- | :--- | :--- | :--- | :--- |
| **`APPROVED`** | 52,102 | 61.85% | 80.51% | 96 (75.00%) |
| **`REVIEW` (Unmapped Recipe Link)** | 19,530 | 23.18% | — | — |
| **`NO_MATCH`** | 8,352 | 9.91% | 12.91% | 23 (17.97%) |
| **`NEEDS_REVIEW`** | 4,262 | 5.06% | 6.59% | 9 (7.03%) |

### 6.3 Direct CNF Measure Feasibility
A recipe ingredient row is directly convertible using CNF data alone if its canonical mapping is `APPROVED`, has a populated CNF food code, and meets either:
* It uses direct mass units (`grams`, `kg`), OR
* Its volume unit matches a valid measure conversion in CNF for that specific food code, OR
* It is a unitless item whose CNF food provides a discrete whole item measure (e.g. onion, tomato, potato, banana, egg).

| Conversion Mechanism | Feasible Row Count | % of All Rows (N=84,246) | Notes |
| :--- | :--- | :--- | :--- |
| **Teaspoons (`tsp`)** | 12,774 | 15.16% | Converted via 5 ml CNF measure |
| **Discrete Whole Items** | 6,942 | 8.24% | Unitless items (e.g. 2 onions) via CNF medium/whole |
| **Cups (`cup`)** | 5,149 | 6.11% | Converted via 250 ml CNF measure |
| **Tablespoons (`tbsp`)** | 4,291 | 5.09% | Converted via 15 ml CNF measure |
| **Cloves (`clove`)** | 1,674 | 1.99% | Converted via CNF garlic clove measure (3.0g) |
| **Direct Mass (`g`, `kg`)** | 946 | 1.12% | Direct mass scaling against 100g edible portion |
| **Milliliters / Liters (`ml`, `l`)** | 90 | 0.11% | Converted via fluid density |
| **Total Directly Convertible** | **31,866** | **37.82%** | **31,521 rows (37.42%) have non-null quantities** |

---

## 7. Edge Cases Catalog

The future nutrition engine must handle 22 specific edge cases identified during this audit:

### 7.1 Unit and Measurement Variants
1. **Metric Mass (`grams`, `gram`, `kg`, `kilograms`):** 2,452 rows. Directly convertible to grams ($1\text{ kg} = 1000\text{ g}$). Milligrams (`mg`) do not occur in the recipe dataset.
2. **Volume Synonyms:**
   * Cups: `cup` (11,371), `cups` (1,818) $\rightarrow$ normalize to 250 ml.
   * Tablespoons: `tablespoon` (6,369), `tablespoons` (3,341), `tbsp` (220) $\rightarrow$ normalize to 15 ml.
   * Teaspoons: `teaspoon` (17,419), `teaspoons` (1,601), `tsp` (664) $\rightarrow$ normalize to 5 ml.
   * Metric Volume: `ml` (189), `liter` (79), `liters` (2) $\rightarrow$ normalize to milliliters.
3. **Discrete Count Units (`clove`, `cloves`):** 2,120 rows. Garlic represents 99.8% of these. Must resolve to CNF Measure 482 (3.0 g per clove).
4. **Linear Dimension Units (`inch`, `inches`):** 1,740 rows. Overwhelmingly ginger root ("1 inch ginger"). CNF does not have an "inch" measure; it provides "1 slice (0.3cm x 2.5cm dia) = 2.2g". A 1-inch cylindrical knob requires an engine rule (typically ~6-8g).
5. **Botanical / Herb Units (`sprig`, `sprigs`, `bunch`):** 1,647 rows. Used for curry leaves, coriander leaves, and mint. Requires standardized herb weight rules (e.g. 1 sprig curry leaves ~0.5g; 1 sprig coriander ~1.5g).
6. **Generic Pieces (`pieces`):** 3 rows. Requires discrete item lookup for the mapped canonical ingredient.
7. **Unitless Quantities (Count Items):** 22,458 rows have a populated quantity but missing unit (e.g. "2 Onions", "3 Tomatoes", "1 Green Chilli"). Must resolve to CNF whole/medium item weights.

### 7.2 Numeric Formatting Edge Cases
8. **Simple Fractions (`1/2`, `1/4`, `3/4`, etc.):** 17,353 rows. Clean string fractions parseable via `fractions.Fraction` or float conversion.
9. **Mixed Fractions (`1 1/2`, `2 1/4`, etc.):** 1,297 rows. Compound strings requiring splitting integer and fraction parts before summation.
10. **Unspaced Mixed Fraction Typos (`11/2`, `21/2`, `11/4`):** 7 rows. E.g., `21/2` meant `2 1/2` (2.5 tsp), but simple fraction parsing evaluates to `10.5`. Engine must intercept `11/2`, `21/2`, `11/4`, `31/2` and map them to their mixed fraction equivalents.
11. **Odd Denominators:** Denominators like `1/12`, `1/5`, `1/6`, `3/8`, `7/8` exist in small quantities and parse accurately with floating point arithmetic.

### 7.3 Qualitative and Range Text
12. **"To Taste" & Subjective Quantities:** 4,995 rows contain "taste" (mostly salt and spices). Must be assigned a sensible default (e.g., 0.5g or 1g for salt) or reported as variable nutrition.
13. **"As Required" / "As Needed":** 1,513 rows (mostly cooking oil, water, or flour for dusting). Oil "as required" presents significant calorie calculation risk if left unmodeled (e.g. defaulting to 1 tbsp / 14g cooking oil per recipe vs. 0g).
14. **Culinary Pinches (`pinch`, `pinches`):** 948 rows (asafoetida, turmeric, salt). Requires standard culinary definition: 1 pinch ~ 0.3g to 0.5g.
15. **Handfuls (`handful`):** 114 rows (coriander, mint, spinach). Requires density approximation (e.g. 1 handful leaves ~ 15g - 20g).
16. **Pre-Parsed Ranges:** 2,008 raw ingredient lines contained ranges (`6 to 8`, `3-4`). Because the upstream parser captured the lower bound in `quantity`, the engine receives a clean integer (`6`, `3`) but must account for the trailing residual string in `ingredient` (e.g. `-4 Curry leaves`).

### 7.4 Data Linkage and Mapping Edge Cases
17. **Both Quantity and Unit Missing:** 10,753 rows (12.76% of dataset). Primarily "Salt - to taste", "Sunflower Oil - as required", "Coriander Leaves - for garnishing".
18. **Unmapped Recipe Ingredients (`REVIEW` status):** 19,530 rows (23.18% of dataset). These ingredients have no canonical mapping and cannot yield nutrition until mapped or defaulted.
19. **Curated `NO_MATCH` Ingredients:** 8,352 rows (9.91% of dataset across 23 canonical ingredients: asafoetida, curry leaves, fenugreek leaves, jaggery, paneer, mutton, chana dal, urad dal, curd, tamarind, etc.). Requires explicit handling: these items provide zero calculated nutrition under strict CNF matching.
20. **Curated `NEEDS_REVIEW` Proxy Mappings:** 4,262 rows (5.06% of dataset across 9 canonical ingredients: whole cardamom pods mapped to ground cardamom; cinnamon stick mapped to ground cinnamon; cumin powder mapped to seed; coriander powder mapped to seed; 2% milk vs whole milk). Nutrition engine must tag proxy nutrition estimates.
21. **Derived / Processed Food State Differences:** 10 curated ingredients map to derived CNF states (e.g. canned tomato puree, sun-dried chili, cocoa powder, almond dried). Density and nutrient concentration differ markedly from fresh states.
22. **Dry vs. Cooked State Ambiguity:** CNF grain and pulse records (`rice`, `toor dal`, `moong dal`) are on a **raw, dry seed basis** (e.g. dry rice: 360 kcal/100g; cooked rice: 130 kcal/100g). Recipe ingredients specifying "cooked rice" or "boiled dal" will be heavily overstated if multiplied directly against raw CNF profiles without yield adjustment.

---

## 8. Risks and Limitations

1. **Coverage Limitation (Unmapped & No-Match Rows):**
   * Currently, 23.18% of recipe ingredient rows are unmapped (`REVIEW`), and 9.91% of recipe rows map to `NO_MATCH` canonical ingredients.
   * If a recipe nutrition calculation engine were run today, **33.09% of all recipe ingredient rows would contribute 0 calories and 0 macros**, leading to systematic undercounting of recipe nutrition.
2. **"Salt to Taste" & Sodium Skew:**
   * Sodium is a core monitored nutrient (`307`). Over 4,300 recipe rows specify salt "to taste" with no numeric quantity. If omitted, sodium in recipes will appear artificially low; if assigned an arbitrary mass (e.g. 5g vs 1g), sodium will fluctuate wildly.
3. **Cooking Oil "As Required" & Caloric Underestimation:**
   * Cooking oil is frequently specified without quantity ("Sunflower Oil - for deep frying", "oil - as per use"). 1 tablespoon of oil is ~120 kcal (100% fat). Omitting unquantified oil creates massive caloric deficits in cooked dish profiles.
4. **Raw vs. Cooked Form Disparity:**
   * Canadian Nutrient File data models agricultural commodities primarily as raw dry pulses/grains or canned/boiled products. Indian recipes frequently state quantities in dry grains (e.g. "1 cup rice") or cooked states ("1 cup cooked rice"). Applying dry raw rice nutrition to cooked volume yields a ~3x caloric overestimation.
5. **Regional Density & Sizing Discrepancies:**
   * CNF measure weights reflect North American agricultural sizes (e.g. "1 large onion = 150g", "1 medium potato = 213g"). Indian kitchen onions and potatoes are typically smaller (70g - 100g).

---

## 9. Recommendations for Implementation Stage

When the project proceeds to implementing the Nutrition Engine, the engine should adhere to the following architecture:

1. **Two-Pass Quantity Normalizer:**
   * Pass 1: Parse string fractions and mixed fractions cleanly (intercepting typo fractions `11/2`, `21/2`, `11/4`).
   * Pass 2: Map qualitative quantities (`to taste`, `pinch`, `handful`, `sprig`, `inch`) through an explicit, configurable **Culinary Default Table** rather than dropping them as zero.
2. **Tiered Unit Conversion Hierarchy:**
   * **Tier 1 (Direct Mass):** If unit is in `{g, grams, kg, kilograms}`, convert directly to grams and evaluate per 100g CNF basis.
   * **Tier 2 (Food-Specific CNF Measure):** If unit is volume (`cup`, `tbsp`, `tsp`) or discrete (`clove`, `medium`, `whole`), look up the exact `Measure_Weight_Conversion` for that `Food_Code`.
   * **Tier 3 (Density Proxy Fallback):** If a volume unit lacks a food-specific measure in CNF, log a conversion warning and use a validated food group density proxy (e.g., vegetable oil density = 0.92 g/ml; fluid dairy = 1.03 g/ml; ground spices = 0.45 g/ml).
3. **Cooked vs. Dry Form State Resolver:**
   * Inspect the `preparation` and `ingredient` columns for state keywords (`cooked`, `boiled`, `steamed`, `soaked`). If a raw dry CNF record is mapped to a recipe requesting cooked yield, apply standard hydration yield factors (e.g., 100g raw rice $\approx$ 250g cooked rice).
4. **Nutrition Engine Status Tagging:**
   * Every computed recipe nutrition record must include data quality provenance:
     * `COMPLETE`: 100% of non-water recipe ingredients successfully mapped and quantified.
     * `APPROXIMATE`: Contains proxy mappings (`NEEDS_REVIEW`), qualitative defaults (`pinch`, `to taste`), or density fallbacks.
     * `PARTIAL`: One or more major caloric ingredients unmapped (`REVIEW` or `NO_MATCH`).
5. **Strict Constraint Preservation:**
   * Keep recipe datasets and CNF reference files completely immutable.
   * Store all recipe-level calculated nutrition in a dedicated output directory (e.g., `data/processed/recipe_nutrition.csv`).
