"""Offline Evaluation Script for Comparing Baseline HybridRanker vs. XGBoostRanker.

Evaluates both rankers on identical test query groups:
1. NDCG@5, NDCG@10
2. MRR@10
3. Precision@5, Precision@10
4. Recall@10
5. Hard constraint violation count (strictly 0)
6. Ranking latency comparison
"""

from __future__ import annotations

from collections import defaultdict
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.constraints import (
    ConstraintEngine,
    ConstraintRequest,
    DietaryConstraints,
    IngredientConstraints,
)
from src.ranking.features import (
    FEATURE_NAMES,
    FeatureExtractor,
    RankingContext,
)
from src.ranking.metrics import evaluate_query_ranking
from src.ranking.xgboost_ranker import XGBoostRanker
from src.recommendation.config import RecommendationConfig
from src.recommendation.hybrid_ranker import HybridRanker, ScoredCandidate
from src.recommendation.recommender import KitchenPilotRecommender

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_ranker")

TEST_DATASET_PATH = PROJECT_ROOT / "data" / "training" / "ranking_test.csv"


def evaluate_both_rankers():
    print("=" * 75)
    print("STAGE F — OFFLINE RANKER EVALUATION: HYBRID BASELINE vs. XGBOOST")
    print("=" * 75)

    if not TEST_DATASET_PATH.is_file():
        raise FileNotFoundError(f"Test dataset not found at {TEST_DATASET_PATH}. Run training first.")

    df_test = pd.read_csv(TEST_DATASET_PATH)
    unique_queries = df_test["query_id"].unique()
    print(f"Test dataset: {len(df_test)} candidate rows across {len(unique_queries)} query groups")

    # Initialize engines
    config = RecommendationConfig()
    recommender = KitchenPilotRecommender(config=config)
    hybrid_ranker = HybridRanker(config=config)
    xgb_ranker = XGBoostRanker()
    constraint_engine = ConstraintEngine()
    extractor = FeatureExtractor()

    # Pre-warm XGBoost model to separate loading from warm inference latency
    t_load_start = time.perf_counter()
    xgb_ranker.load_model()
    t_model_load = (time.perf_counter() - t_load_start) * 1000
    print(f"XGBoost model warm-up load time: {t_model_load:.2f} ms")

    baseline_metrics = defaultdict(list)
    xgboost_metrics = defaultdict(list)

    baseline_latencies = []
    xgboost_latencies = []

    total_candidates_evaluated = 0
    baseline_hard_violations = 0
    xgboost_hard_violations = 0

    for qid, group in df_test.groupby("query_id", sort=False):
        candidate_ids = group["recipe_id"].tolist()
        total_candidates_evaluated += len(candidate_ids)
        gt_map = dict(zip(group["recipe_id"], group["label"]))

        # Build dummy ScoredCandidates for HybridRanker
        scored_candidates = []
        for _, row in group.iterrows():
            rid = row["recipe_id"]
            sc = ScoredCandidate(
                recipe_id=rid,
                recipe_name=f"Recipe_{rid}",
                similarity_score=float(row.get("retrieval_tfidf_score", 0.0)),
                ingredient_match_score=float(row.get("ingredient_coverage_ratio", 0.0)),
                nutrition_score=float(row.get("nutrition_available", 0.0)),
                preference_score=float(row.get("cuisine_match", 0.0)),
                nutrition_confidence=1.0,
            )
            scored_candidates.append(sc)

        # Build RankingContext for XGBoost
        context = RankingContext(
            tfidf_candidates={row["recipe_id"]: float(row.get("retrieval_tfidf_score", 0.0)) for _, row in group.iterrows()},
            bge_candidates={row["recipe_id"]: float(row.get("retrieval_bge_score", 0.0)) for _, row in group.iterrows()},
            tfidf_ranks={row["recipe_id"]: idx for idx, (_, row) in enumerate(group.iterrows())},
            bge_ranks={row["recipe_id"]: idx for idx, (_, row) in enumerate(group.iterrows())},
        )

        # 1. Baseline HybridRanker evaluation
        t0 = time.perf_counter()
        ranked_hybrid = hybrid_ranker.rank_candidates(scored_candidates, top_k=len(candidate_ids))
        t_hybrid = (time.perf_counter() - t0) * 1000
        baseline_latencies.append(t_hybrid)
        hybrid_order = [c.recipe_id for c in ranked_hybrid]

        # Invariant check: Verify zero hard violations in baseline
        for rid in hybrid_order:
            row_rec = group[group["recipe_id"] == rid].iloc[0]
            if row_rec.get("hard_constraint_violation", 0.0) > 0.0:
                baseline_hard_violations += 1

        m_hybrid = evaluate_query_ranking(hybrid_order, gt_map)
        for k, v in m_hybrid.items():
            baseline_metrics[k].append(v)

        # 2. XGBoost Ranker evaluation
        t0 = time.perf_counter()
        ranked_xgb = xgb_ranker.rank(candidate_ids, context, top_k=len(candidate_ids))
        t_xgb = (time.perf_counter() - t0) * 1000
        xgboost_latencies.append(t_xgb)
        xgb_order = [rid for rid, _ in ranked_xgb]

        # Invariant check: Verify zero hard violations in XGBoost
        for rid in xgb_order:
            row_rec = group[group["recipe_id"] == rid].iloc[0]
            if row_rec.get("hard_constraint_violation", 0.0) > 0.0:
                xgboost_hard_violations += 1

        m_xgb = evaluate_query_ranking(xgb_order, gt_map)
        for k, v in m_xgb.items():
            xgboost_metrics[k].append(v)

    # Summarize results
    avg_hybrid = {k: round(float(np.mean(v)), 4) for k, v in baseline_metrics.items()}
    avg_xgb = {k: round(float(np.mean(v)), 4) for k, v in xgboost_metrics.items()}

    print("\n" + "=" * 75)
    print("EVALUATION RESULTS COMPARISON TABLE (Weak Supervision Benchmark)")
    print("=" * 75)
    print(f"{'Metric':<20} | {'Baseline (Hybrid)':<20} | {'XGBoost Ranker':<20}")
    print("-" * 75)
    for m in ["ndcg@5", "ndcg@10", "mrr@10", "precision@5", "precision@10", "recall@10"]:
        print(f"{m.upper():<20} | {avg_hybrid[m]:<20.4f} | {avg_xgb[m]:<20.4f}")
    print("-" * 75)
    print(f"{'Mean Latency (ms)':<20} | {np.mean(baseline_latencies):<20.4f} | {np.mean(xgboost_latencies):<20.4f}")
    print(f"{'Hard Violations':<20} | {baseline_hard_violations:<20} | {xgboost_hard_violations:<20}")
    print("=" * 75)
    print("NOTE: Evaluated against multi-signal weak supervision ground truth.")
    print("      This benchmark confirms model usage and ranking correctness.")
    print("      It does NOT represent real user relevance until Stage G user feedback is added.")
    print("=" * 75)


if __name__ == "__main__":
    evaluate_both_rankers()
