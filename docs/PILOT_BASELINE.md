# KitchenPilot-V1 — Controlled Pilot Baseline Architecture & Model Freeze

## 1. Executive Summary & Purpose

During **Stage K (Controlled Pilot Execution & Genuine Feedback Collection)**, the recommendation pipeline is explicitly **frozen**. No ML model weights, retrieval indexes, feature schemas, or ranking parameters are adjusted in response to early pilot participant engagement.

This document establishes the official **Recommendation Quality Baseline** for KitchenPilot-V1. Preserving these exact artifact hashes, schemas, and configurations guarantees that interaction data gathered during Pilot Period A and any subsequent Pilot Period B can be evaluated against a static, scientifically sound benchmark without conflating algorithmic shifts with participant behavioral dynamics.

---

## 2. Frozen Production Model Specifications

| Parameter | Specification |
|---|---|
| **Production Model ID** | `xgb_ranker_v0.1.0` |
| **Model Type** | Gradient Boosted Decision Tree (XGBoost `rank:pairwise` / LambdaMART) |
| **Model Artifact Path** | `models/ranking/xgboost_ranker.json` |
| **Model SHA256 Checksum** | `8d00370fb80f81de6e889a1c6b75290063284a3964de85a2a9acc502b0d6677b` |
| **Training Dataset Version** | `1.0.0` (Curated India Recipes Catalog) |
| **Feature Schema Version** | `1.0.0` (30 Total Features) |
| **Offline Performance Baseline** | NDCG@5: `0.8841`, NDCG@10: `0.9126`, MRR@10: `0.9412` |
| **Stage Promotion Status** | Promoted & Frozen in Stage I (`ACTIVE_PRODUCTION`) |

---

## 3. Retrieval Pipeline Baseline

KitchenPilot-V1 employs a hybrid two-tier retrieval architecture producing up to 100 candidate recipes for the constraint and ranking engines:

### 3.1 Sparse Lexical Retrieval (TF-IDF)
- **Artifact:** `models/tfidf_vectorizer.joblib` & `models/tfidf_recipe_matrix.npz`
- **Scope:** Recipe title, cuisine, course, and normalized ingredient tokens
- **Sub-linear TF Scaling:** Enabled (`sublinear_tf=True`)
- **N-gram Range:** `(1, 2)`
- **Candidate Contribution:** Top-50 lexical matches

### 3.2 Dense Semantic Retrieval (BGE)
- **Model:** `BAAI/bge-small-en-v1.5`
- **Embedding Dimension:** 384
- **Similarity Metric:** Cosine similarity
- **Vector Index:** Normalized FAISS / NumPy dot-product semantic matrix
- **Candidate Contribution:** Top-50 semantic matches

### 3.3 Hybrid Fusion
- **Candidate Merging:** Union deduplication preserving dense and sparse retrieval ranks
- **Output:** 50–100 candidate recipes passed to the Hard Constraint Engine

---

## 4. Hard Constraint Engine Configuration

The Hard Constraint Engine acts as a non-negotiable filter. **Hard constraints must always execute before ranking and personalization.**

### 4.1 Filter Hierarchy
```text
Candidate Retrieval (50–100 recipes)
        ↓
Hard Constraint Engine (Strict Zero-Violation Filtering)
        ↓
XGBoost Ranking Engine (L2R Scoring)
        ↓
Personalization & Diversity Layer (Top-K Output)
```

### 4.2 Invariant Hard Constraints
1. **Dietary Classification:**
   - `vegetarian`: Excludes all non-vegetarian items (meat, poultry, seafood).
   - `vegan`: Excludes all animal-derived ingredients (meat, dairy, honey).
   - `jain`: Excludes all root vegetables (onion, garlic, potato, carrot, radish) and non-veg.
   - `satvik`: Excludes onion, garlic, mushrooms, alcohol, and stale items.
2. **Allergen Exclusions:**
   - Absolute exclusion of recipes containing user-flagged allergens (peanuts, tree nuts, milk, eggs, wheat/gluten, soy, shellfish, fish).
3. **Calorie & Preparation Thresholds:**
   - Max calories per serving ceiling (if specified).
   - Maximum cooking time limit (if specified).

**Relaxation Policy:** Hard constraints are **never** silently relaxed to increase engagement or prevent empty results. If no candidates survive, the system explicitly returns zero results with diagnostic metadata.

---

## 5. Feature Schema Baseline (30 Features)

The XGBoost ranker operates on a strict 30-feature vector (`v1.0.0`):

### 5.1 Base Lexical & Catalog Features (12)
1. `bm25_score`: Lexical relevance score
2. `tfidf_score`: Sparse vector cosine similarity
3. `query_title_overlap`: Jaccard token overlap between query and recipe title
4. `query_ingredient_overlap`: Token overlap between query and ingredients
5. `prep_time_minutes`: Preparation duration in minutes
6. `cook_time_minutes`: Cooking duration in minutes
7. `total_time_minutes`: Total duration in minutes
8. `ingredient_count`: Total number of ingredients
9. `instruction_length`: Word count of recipe instructions
10. `cuisine_match`: Binary match against query cuisine
11. `course_match`: Binary match against query course
12. `diet_match`: Binary match against query dietary filter

### 5.2 Dense Semantic Features (4)
13. `bge_semantic_similarity`: Cosine similarity from `BAAI/bge-small-en-v1.5`
14. `dense_rank`: Dense retrieval rank index
15. `sparse_rank`: Sparse retrieval rank index
16. `reciprocal_rank_fusion_score`: Hybrid RRF score

### 5.3 Nutritional & Health Features (7)
17. `calories_per_serving`: Energy in kcal
18. `protein_g`: Protein content in grams
19. `carbohydrates_g`: Carbohydrate content in grams
20. `fat_g`: Total fat content in grams
21. `fiber_g`: Dietary fiber in grams
22. `sodium_mg`: Sodium content in milligrams
23. `nutrition_profile_balance_score`: Harmonic balance across macronutrients

### 5.4 Personalization & Historical Context Features (7)
24. `user_pantry_overlap_ratio`: Percentage of recipe ingredients present in user's pantry
25. `user_pantry_missing_count`: Count of missing ingredients
26. `user_cuisine_affinity_score`: Historical user preference for recipe cuisine
27. `user_past_positive_feedback_count`: Number of prior LIKE/SAVE/COOKED events for this recipe
28. `user_past_negative_feedback_count`: Number of prior DISLIKE/HIDE events for this recipe
29. `user_nutrition_target_alignment`: Cosine distance between user target macros and recipe macros
30. `recipe_popularity_prior`: Global prior engagement log-count

---

## 6. Personalization Heuristics Baseline

1. **Pantry Matching:** Recipes with higher ingredient coverage receive non-linear pantry match boosting.
2. **Negative Feedback Penalty:** Recipes explicitly marked `DISLIKE` or `HIDE` by the authenticated user are severely penalized or omitted.
3. **Diversity Preservation:** Maximal Marginal Relevance (MMR) penalty applied across redundant dishes to ensure diversity across cuisines and main ingredients.

---

## 7. Pilot Period Preservation Protocol

To ensure reproducible comparison:
1. **No Online Model Updates:** Models are never updated dynamically online during the pilot.
2. **Audit Period Comparison:** When comparing Pilot Period A to Pilot Period B:
   - Changes in CTR, Save rate, or Cook rate reflect purely participant behavior and onboarding quality.
   - Any proposed model retraining must strictly obey the Stage I sufficiency thresholds (≥ 200 interactions, ≥ 20 users, ≥ 50 recipes, ≥ 30 query sessions, ≥ 7 days).
