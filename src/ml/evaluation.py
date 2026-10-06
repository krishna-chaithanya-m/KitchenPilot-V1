"""Model evaluation and comparative safety gates against production baseline for Stage I."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb

from src.ml.config import (
    EVALUATION_REPORTS_DIR,
    GATE_MAX_HARD_CONSTRAINT_VIOLATIONS,
    GATE_MAX_INFERENCE_LATENCY_P95_MS,
    GATE_MAX_ZERO_RESULT_RATE_PCT,
    GATE_MIN_MRR10_IMPROVEMENT_PCT,
    GATE_MIN_NDCG5_IMPROVEMENT_PCT,
)
from src.ml.registry import compute_file_sha256
from src.ranking.features import FEATURE_NAMES

logger = logging.getLogger("kitchenpilot.ml.evaluation")


@dataclass
class ModelComparisonMetrics:
    """Evaluation metrics comparing production baseline vs candidate on identical test split."""
    production_metrics: Dict[str, float]
    candidate_metrics: Dict[str, float]
    relative_improvements: Dict[str, float]
    gate_results: Dict[str, bool]
    passed_all_gates: bool
    summary: str


def compute_ranking_metrics_for_booster(
    booster: xgb.Booster,
    test_features: np.ndarray,
    test_labels: np.ndarray,
    test_query_groups: List[int],
) -> Dict[str, float]:
    """Compute NDCG@K, MRR@10, and Precision@K for a Booster instance."""
    if len(test_query_groups) == 0:
        return {}

    dtest = xgb.DMatrix(test_features)
    preds = booster.predict(dtest)

    ndcg5_list, ndcg10_list, mrr10_list, p5_list, p10_list = [], [], [], [], []

    curr_idx = 0
    for group_size in test_query_groups:
        end_idx = curr_idx + group_size
        group_preds = preds[curr_idx:end_idx]
        group_labels = test_labels[curr_idx:end_idx]
        curr_idx = end_idx

        # Sort by predicted score descending
        ranked_indices = np.argsort(-group_preds)
        sorted_labels = group_labels[ranked_indices]

        # Precision@5, Precision@10 (relevant if label >= 2)
        top5 = [1 if r >= 2 else 0 for r in sorted_labels[:5]]
        top10 = [1 if r >= 2 else 0 for r in sorted_labels[:10]]
        p5_list.append(sum(top5) / 5.0)
        p10_list.append(sum(top10) / 10.0)

        # MRR@10
        mrr = 0.0
        for rank_idx, rel in enumerate(top10, 1):
            if rel == 1:
                mrr = 1.0 / rank_idx
                break
        mrr10_list.append(mrr)

        # NDCG@K
        def _dcg(rels: np.ndarray, k: int) -> float:
            sub = rels[:k]
            return sum((2**r - 1) / np.log2(i + 2) for i, r in enumerate(sub))

        dcg5 = _dcg(sorted_labels, 5)
        ideal = np.sort(sorted_labels)[::-1]
        idcg5 = _dcg(ideal, 5)
        ndcg5_list.append(dcg5 / idcg5 if idcg5 > 0 else 0.0)

        dcg10 = _dcg(sorted_labels, 10)
        idcg10 = _dcg(ideal, 10)
        ndcg10_list.append(dcg10 / idcg10 if idcg10 > 0 else 0.0)

    return {
        "ndcg@5": round(float(np.mean(ndcg5_list)), 4) if ndcg5_list else 0.0,
        "ndcg@10": round(float(np.mean(ndcg10_list)), 4) if ndcg10_list else 0.0,
        "mrr@10": round(float(np.mean(mrr10_list)), 4) if mrr10_list else 0.0,
        "precision@5": round(float(np.mean(p5_list)), 4) if p5_list else 0.0,
        "precision@10": round(float(np.mean(p10_list)), 4) if p10_list else 0.0,
    }


def compare_models(
    production_model_path: Path,
    candidate_model_path: Path,
    test_features: np.ndarray,
    test_labels: np.ndarray,
    test_query_groups: List[int],
    constraint_violations: int = 0,
    zero_result_rate: float = 0.0,
    candidate_p95_latency_ms: float = 85.0,
) -> ModelComparisonMetrics:
    """Run head-to-head evaluation against identical held-out test data and evaluate safety gates."""
    prod_booster = xgb.Booster()
    prod_booster.load_model(str(production_model_path))

    cand_booster = xgb.Booster()
    cand_booster.load_model(str(candidate_model_path))

    prod_metrics = compute_ranking_metrics_for_booster(
        prod_booster, test_features, test_labels, test_query_groups
    )
    cand_metrics = compute_ranking_metrics_for_booster(
        cand_booster, test_features, test_labels, test_query_groups
    )

    # Relative improvement
    rel_improvements = {}
    for metric, c_val in cand_metrics.items():
        p_val = prod_metrics.get(metric, 0.0)
        if p_val > 0:
            rel_improvements[metric] = round(((c_val - p_val) / p_val) * 100.0, 2)
        else:
            rel_improvements[metric] = 0.0

    # Acceptance Gates
    ndcg5_delta = rel_improvements.get("ndcg@5", 0.0)
    mrr10_delta = rel_improvements.get("mrr@10", 0.0)

    gates = {
        "gate_zero_constraint_violations": constraint_violations <= GATE_MAX_HARD_CONSTRAINT_VIOLATIONS,
        "gate_ndcg5_non_negative": ndcg5_delta >= GATE_MIN_NDCG5_IMPROVEMENT_PCT,
        "gate_mrr10_non_negative": mrr10_delta >= GATE_MIN_MRR10_IMPROVEMENT_PCT,
        "gate_zero_result_rate": zero_result_rate <= GATE_MAX_ZERO_RESULT_RATE_PCT,
        "gate_latency_budget": candidate_p95_latency_ms <= GATE_MAX_INFERENCE_LATENCY_P95_MS,
    }

    all_passed = all(gates.values())
    summary = (
        "Candidate model passed all quality and safety gates."
        if all_passed
        else f"Candidate model failed gates: {[g for g, p in gates.items() if not p]}"
    )

    result = ModelComparisonMetrics(
        production_metrics=prod_metrics,
        candidate_metrics=cand_metrics,
        relative_improvements=rel_improvements,
        gate_results=gates,
        passed_all_gates=all_passed,
        summary=summary,
    )

    # Persist report
    EVALUATION_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = EVALUATION_REPORTS_DIR / f"eval_report_{candidate_model_path.stem}.json"
    report_file.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result
