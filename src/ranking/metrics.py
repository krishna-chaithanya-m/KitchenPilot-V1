"""Ranking and evaluation metrics for Stage F Learning-to-Rank.

Implements standard information retrieval and ranking metrics:
1. NDCG@K (Normalized Discounted Cumulative Gain at rank K)
2. MRR@K (Mean Reciprocal Rank at rank K)
3. Precision@K (Proportion of relevant candidates in top K)
4. Recall@K (Proportion of total relevant candidates retrieved in top K)
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Union


def dcg_at_k(relevance_scores: Sequence[Union[int, float]], k: int) -> float:
    """Compute Discounted Cumulative Gain at rank K."""
    dcg = 0.0
    for i, rel in enumerate(relevance_scores[:k]):
        if rel > 0:
            dcg += (2.0 ** float(rel) - 1.0) / math.log2(float(i) + 2.0)
    return dcg


def ndcg_at_k(
    predicted_relevances: Sequence[Union[int, float]],
    true_relevances: Sequence[Union[int, float]],
    k: int,
) -> float:
    """Compute Normalized Discounted Cumulative Gain at rank K.

    Handles zero ideal DCG edge cases gracefully.
    """
    ideal_relevances = sorted(true_relevances, reverse=True)
    idcg = dcg_at_k(ideal_relevances, k)
    if idcg <= 0.0:
        return 0.0
    actual_dcg = dcg_at_k(predicted_relevances, k)
    return min(1.0, max(0.0, actual_dcg / idcg))


def mrr_at_k(
    predicted_relevances: Sequence[Union[int, float]],
    k: int,
    relevance_threshold: float = 1.0,
) -> float:
    """Compute Mean Reciprocal Rank at rank K."""
    for i, rel in enumerate(predicted_relevances[:k]):
        if float(rel) >= relevance_threshold:
            return 1.0 / (float(i) + 1.0)
    return 0.0


def precision_at_k(
    predicted_relevances: Sequence[Union[int, float]],
    k: int,
    relevance_threshold: float = 1.0,
) -> float:
    """Compute Precision at rank K."""
    if k <= 0:
        return 0.0
    top_k = predicted_relevances[:k]
    relevant = sum(1 for rel in top_k if float(rel) >= relevance_threshold)
    return float(relevant) / float(k)


def recall_at_k(
    predicted_relevances: Sequence[Union[int, float]],
    true_relevances: Sequence[Union[int, float]],
    k: int,
    relevance_threshold: float = 1.0,
) -> float:
    """Compute Recall at rank K."""
    total_relevant = sum(1 for rel in true_relevances if float(rel) >= relevance_threshold)
    if total_relevant <= 0:
        return 0.0
    top_k = predicted_relevances[:k]
    retrieved_relevant = sum(1 for rel in top_k if float(rel) >= relevance_threshold)
    return min(1.0, float(retrieved_relevant) / float(total_relevant))


def evaluate_query_ranking(
    candidate_recipe_ids_ranked: Sequence[str],
    recipe_ground_truth: Dict[str, float],
    k_values: Sequence[int] = (5, 10),
    relevance_threshold: float = 1.0,
) -> Dict[str, float]:
    """Evaluate a single ranked query result against ground truth or weak labels."""
    predicted_rels = [float(recipe_ground_truth.get(rid, 0.0)) for rid in candidate_recipe_ids_ranked]
    all_true_rels = list(recipe_ground_truth.values())

    metrics: Dict[str, float] = {}
    for k in k_values:
        metrics[f"ndcg@{k}"] = ndcg_at_k(predicted_rels, all_true_rels, k=k)
        metrics[f"precision@{k}"] = precision_at_k(predicted_rels, k=k, relevance_threshold=relevance_threshold)
        metrics[f"recall@{k}"] = recall_at_k(predicted_rels, all_true_rels, k=k, relevance_threshold=relevance_threshold)

    metrics["mrr@10"] = mrr_at_k(predicted_rels, k=10, relevance_threshold=relevance_threshold)
    return metrics
