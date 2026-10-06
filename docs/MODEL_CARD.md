# KitchenPilot-V1 — Model Card: Production XGBoost Ranker

## Model Details
- **Model Name:** `xgboost_ranker`
- **Active Production Version:** `xgb_ranker_v0.1.0`
- **Objective:** `rank:ndcg`
- **Library Version:** XGBoost 3.4.1
- **Feature Schema Version:** `1.0.0` (30 dense features)
- **Dataset Version:** `1.0.0` (6,871 recipes)
- **Artifact SHA-256:** `8d00370fb80f81de6e889a1c6b75290063284a3964de85a2a9acc502b0d6677b`
- **Parent Model:** None (Stage F Baseline)

## Hyperparameters
- `n_estimators`: 80
- `max_depth`: 4
- `learning_rate`: 0.08
- `subsample`: 0.85
- `colsample_bytree`: 0.85
- `random_seed`: 42

## Intended Use
- **Primary Use:** Offline-trained Learning-to-Rank candidate re-ranking of Indian recipe candidates that have already satisfied Stage E deterministic hard dietary, allergen, and nutrition constraints.
- **Out of Scope:** Unconstrained filtering, real-time online model retraining, medical nutrition therapy, or unstructured raw web search.

## Safety & Governance
- Hard constraints strictly precede ranker scoring. The ranker cannot restore eliminated non-compliant candidates.
- Zero feedback mutations at runtime.
- Model replacements require explicit administrative promotion through `scripts/model_registry_cli.py`.
