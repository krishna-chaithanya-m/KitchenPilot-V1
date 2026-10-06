"""Offline Training Pipeline for Stage F XGBoost Learning-to-Rank.

Trains a GBDT ranking model using XGBoost with native rank:ndcg objective:
1. Generates or loads versioned query-group datasets
2. Splits cleanly by query group (Train 70% / Val 15% / Test 15%)
3. Exports stable feature schema metadata
4. Trains XGBoost ranking booster with group boundaries
5. Computes ranking metrics (NDCG@K, MRR@K, Precision@K, Recall@K)
6. Computes feature importance (Gain, Weight, Cover)
7. Saves native JSON model artifact and metadata
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import xgboost as xgb

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ranking.dataset import (
    DATASET_VERSION,
    RankingDatasetBuilder,
)
from src.ranking.features import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    FeatureExtractor,
)
from src.ranking.metrics import (
    evaluate_query_ranking,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("train_xgboost_ranker")

MODELS_DIR = PROJECT_ROOT / "models" / "ranking"
DATA_TRAINING_DIR = PROJECT_ROOT / "data" / "training"
MODEL_VERSION = "0.1.0"


def train_ranker(
    num_queries: int = 120,
    random_seed: int = 42,
    n_estimators: int = 80,
    max_depth: int = 4,
    learning_rate: float = 0.08,
) -> None:
    print("=" * 70)
    print("STAGE F — XGBOOST LEARNING-TO-RANK TRAINING PIPELINE")
    print("=" * 70)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_TRAINING_DIR.mkdir(parents=True, exist_ok=True)

    from collections import defaultdict

    # 1. Feature Extractor & Schema Export
    extractor = FeatureExtractor()
    schema_path = MODELS_DIR / "feature_schema.json"
    extractor.save_feature_schema(schema_path)

    # 2. Build or Load Dataset
    train_csv = DATA_TRAINING_DIR / "ranking_train.csv"
    val_csv = DATA_TRAINING_DIR / "ranking_validation.csv"
    test_csv = DATA_TRAINING_DIR / "ranking_test.csv"

    if train_csv.is_file() and val_csv.is_file() and test_csv.is_file():
        print(f"Loading existing ranking datasets from {DATA_TRAINING_DIR}...")
        df_train = pd.read_csv(train_csv)
        df_val = pd.read_csv(val_csv)
        df_test = pd.read_csv(test_csv)
        full_df = pd.concat([df_train, df_val, df_test], ignore_index=True)
    else:
        builder = RankingDatasetBuilder(feature_extractor=extractor)
        print(f"Generating weak-supervision ranking dataset ({num_queries} queries)...")
        full_df = builder.generate_weak_supervision_dataset(
            num_queries=num_queries,
            candidates_per_query=40,
            random_seed=random_seed,
        )

        # 3. Deterministic Group Split
        df_train, df_val, df_test = builder.split_by_query_group(
            full_df,
            train_ratio=0.70,
            val_ratio=0.15,
            test_ratio=0.15,
            random_seed=random_seed,
        )

        # Save dataset artifacts
        df_train.to_csv(train_csv, index=False)
        df_val.to_csv(val_csv, index=False)
        df_test.to_csv(test_csv, index=False)

    print(f"Dataset partitions loaded:")
    print(f"  Train: {len(df_train)} rows ({df_train['query_id'].nunique()} queries)")
    print(f"  Val:   {len(df_val)} rows ({df_val['query_id'].nunique()} queries)")
    print(f"  Test:  {len(df_test)} rows ({df_test['query_id'].nunique()} queries)")

    # 4. Prepare DMatrix with Group Boundaries
    def prepare_dmatrix(df: pd.DataFrame) -> Tuple[xgb.DMatrix, List[int]]:
        # Sort strictly by query_id so groups are contiguous
        df_sorted = df.sort_values(by="query_id").reset_index(drop=True)
        groups = df_sorted.groupby("query_id", sort=False).size().tolist()

        X = df_sorted[FEATURE_NAMES].values.astype(np.float32)
        y = df_sorted["label"].values.astype(np.float32)

        dmat = xgb.DMatrix(X, label=y, feature_names=FEATURE_NAMES)
        dmat.set_group(groups)
        return dmat, groups

    dtrain, train_groups = prepare_dmatrix(df_train)
    dval, val_groups = prepare_dmatrix(df_val)
    dtest, test_groups = prepare_dmatrix(df_test)

    # 5. Model Parameters
    params = {
        "objective": "rank:ndcg",
        "eval_metric": ["ndcg@5", "ndcg@10"],
        "max_depth": max_depth,
        "learning_rate": learning_rate,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "min_child_weight": 2.0,
        "reg_lambda": 1.0,
        "random_state": random_seed,
        "tree_method": "hist",
    }

    print("\nTraining XGBoost ranking booster...")
    evals = [(dtrain, "train"), (dval, "val")]
    booster = xgb.train(
        params,
        dtrain,
        num_boost_round=n_estimators,
        evals=evals,
        verbose_eval=20,
    )

    # 6. Save Model in Native Format
    model_path = MODELS_DIR / "xgboost_ranker.json"
    booster.save_model(str(model_path))
    print(f"\nModel artifact saved to {model_path}")

    # 7. Evaluate on Test Query Groups
    df_test_sorted = df_test.sort_values(by="query_id").reset_index(drop=True)
    test_preds = booster.predict(dtest)
    df_test_sorted["predicted_score"] = test_preds

    test_metrics: Dict[str, List[float]] = defaultdict(list)

    for qid, group in df_test_sorted.groupby("query_id", sort=False):
        # Rank by predicted score descending, recipe_id ascending for tie-break
        ranked = group.sort_values(
            by=["predicted_score", "recipe_id"],
            ascending=[False, True]
        )["recipe_id"].tolist()

        gt_map = dict(zip(group["recipe_id"], group["label"]))
        q_m = evaluate_query_ranking(ranked, gt_map)
        for k, v in q_m.items():
            test_metrics[k].append(v)

    avg_test_metrics = {k: round(float(np.mean(v)), 4) for k, v in test_metrics.items()}
    print("\n--- Test Set Evaluation Metrics (Weak Supervision) ---")
    for k, v in avg_test_metrics.items():
        print(f"  {k.upper()}: {v:.4f}")

    # 8. Feature Importance
    importance_gain = booster.get_score(importance_type="gain")
    importance_weight = booster.get_score(importance_type="weight")
    importance_cover = booster.get_score(importance_type="cover")

    sorted_features_gain = sorted(importance_gain.items(), key=lambda x: x[1], reverse=True)
    print("\n--- Top 10 Features by Gain ---")
    for fname, g in sorted_features_gain[:10]:
        print(f"  {fname:<30}: {g:.4f}")

    # 9. Save Metadata
    metadata = {
        "model_name": "xgboost_ranker",
        "model_version": f"xgb_ranker_v{MODEL_VERSION}",
        "feature_version": FEATURE_SCHEMA_VERSION,
        "dataset_version": DATASET_VERSION,
        "status": "trained",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "xgboost_version": xgb.__version__,
        "objective": params["objective"],
        "hyperparameters": {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "subsample": params["subsample"],
            "colsample_bytree": params["colsample_bytree"],
            "random_seed": random_seed,
        },
        "dataset_statistics": {
            "total_queries": full_df["query_id"].nunique(),
            "total_rows": len(full_df),
            "train_queries": len(train_groups),
            "train_rows": len(df_train),
            "val_queries": len(val_groups),
            "val_rows": len(df_val),
            "test_queries": len(test_groups),
            "test_rows": len(df_test),
        },
        "evaluation_metrics": avg_test_metrics,
        "feature_importance_top10_gain": dict(sorted_features_gain[:10]),
        "label_type": "weak_supervision_multi_signal",
        "label_disclaimer": "This model has not been trained on real user interaction data. Weak labels represent synthetic heuristics for infrastructure validation.",
    }

    metadata_path = MODELS_DIR / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"Model metadata saved to {metadata_path}")
    print("=" * 70)


if __name__ == "__main__":
    train_ranker()
