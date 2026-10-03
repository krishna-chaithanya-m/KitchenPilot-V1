"""Offline Recommendation Evaluation Metrics for KitchenPilot-V1.

Implements catalog coverage, intra-list diversity, response time benchmarks,
score distribution, and determinism verification.
Note: For V1, Precision@K and Recall@K are reported as 'Ground truth unavailable'
since no historical user interaction logs exist.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from src.recommendation.config import RecommendationConfig
from src.recommendation.recommender import KitchenPilotRecommender


class RecommendationMetricsEvaluator:
    """Evaluates recommendation engine offline across diverse test query suites."""

    def __init__(
        self,
        recommender: KitchenPilotRecommender,
        config: Optional[RecommendationConfig] = None,
    ) -> None:
        self.recommender = recommender
        self.config = config or RecommendationConfig()
        self.total_catalog_size = len(self.recommender.tfidf_model.recipe_ids)

    def compute_intra_list_diversity(self, recipe_ids: List[str]) -> float:
        """Calculate average pairwise cosine distance (1 - similarity) among recommended items."""
        if len(recipe_ids) < 2:
            return 1.0

        model = self.recommender.tfidf_model
        valid_indices = [
            model.recipe_to_row[rid]
            for rid in recipe_ids
            if rid in model.recipe_to_row
        ]
        if len(valid_indices) < 2:
            return 1.0

        sub_matrix = model.tfidf_matrix[valid_indices]
        sim_matrix = cosine_similarity(sub_matrix)

        # Average upper triangle pairwise similarities
        n = len(valid_indices)
        triu_indices = np.triu_indices(n, k=1)
        pairwise_sims = sim_matrix[triu_indices]

        avg_sim = float(np.mean(pairwise_sims)) if len(pairwise_sims) > 0 else 0.0
        diversity = 1.0 - avg_sim
        return round(float(np.clip(diversity, 0.0, 1.0)), 4)

    def evaluate(
        self,
        queries: Optional[List[Dict[str, Any]]] = None,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """Run comprehensive offline evaluation."""
        if queries is None:
            # Standard representative query suite using valid catalog recipe IDs
            sample_rids = self.recommender.tfidf_model.recipe_ids[:5]
            queries = [{"query_recipe_id": rid} for rid in sample_rids] + [
                {"available_ingredients": ["rice", "onion", "tomato", "cumin", "turmeric"]},
                {"available_ingredients": ["paneer", "butter", "cream", "tomato", "ginger"]},
                {"available_ingredients": ["chicken", "curd", "ginger", "garlic", "chilli"]},
                {"available_ingredients": ["moong dal", "ghee", "cumin", "turmeric"]},
                {"available_ingredients": ["potato", "cauliflower", "onion", "garlic"]},
            ]

        latencies_ms: List[float] = []
        all_recommended_ids: Set[str] = set()
        all_scores: List[float] = []
        diversities: List[float] = []

        for q in queries:
            t0 = time.perf_counter()
            res_df = self.recommender.recommend(
                query_recipe_id=q.get("query_recipe_id"),
                available_ingredients=q.get("available_ingredients"),
                user_preferences=q.get("user_preferences"),
                nutrition_goals=q.get("nutrition_goals"),
                top_k=top_k,
                save_results=False,
            )
            lat = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(lat)

            if not res_df.empty:
                rids = res_df["recipe_id"].tolist()
                all_recommended_ids.update(rids)
                all_scores.extend(res_df["hybrid_score"].tolist())
                div = self.compute_intra_list_diversity(rids)
                diversities.append(div)

        # Determinism check: run query 0 twice and compare exact results
        det_q = queries[0]
        run1 = self.recommender.recommend(
            query_recipe_id=det_q.get("query_recipe_id"),
            available_ingredients=det_q.get("available_ingredients"),
            user_preferences=det_q.get("user_preferences"),
            nutrition_goals=det_q.get("nutrition_goals"),
            top_k=top_k,
            save_results=False,
        )
        run2 = self.recommender.recommend(
            query_recipe_id=det_q.get("query_recipe_id"),
            available_ingredients=det_q.get("available_ingredients"),
            user_preferences=det_q.get("user_preferences"),
            nutrition_goals=det_q.get("nutrition_goals"),
            top_k=top_k,
            save_results=False,
        )
        is_deterministic = bool(
            list(run1["recipe_id"]) == list(run2["recipe_id"])
            and np.allclose(run1["hybrid_score"], run2["hybrid_score"])
        )

        catalog_coverage = len(all_recommended_ids) / self.total_catalog_size if self.total_catalog_size else 0.0
        avg_diversity = float(np.mean(diversities)) if diversities else 0.0
        avg_latency = float(np.mean(latencies_ms)) if latencies_ms else 0.0

        score_arr = np.array(all_scores) if all_scores else np.array([0.0])

        return {
            "precision_at_k": "Ground truth unavailable",
            "recall_at_k": "Ground truth unavailable",
            "catalog_coverage": round(catalog_coverage, 4),
            "unique_recommendations_count": len(all_recommended_ids),
            "total_catalog_size": self.total_catalog_size,
            "average_intra_list_diversity": round(avg_diversity, 4),
            "average_response_time_ms": round(avg_latency, 2),
            "min_response_time_ms": round(float(np.min(latencies_ms)), 2),
            "max_response_time_ms": round(float(np.max(latencies_ms)), 2),
            "score_distribution": {
                "mean": round(float(np.mean(score_arr)), 4),
                "min": round(float(np.min(score_arr)), 4),
                "max": round(float(np.max(score_arr)), 4),
                "std": round(float(np.std(score_arr)), 4),
            },
            "is_deterministic": is_deterministic,
        }
