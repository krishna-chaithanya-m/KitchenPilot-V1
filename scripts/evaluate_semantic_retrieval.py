"""Stage D Semantic Retrieval Evaluation Script for KitchenPilot-V1.

Evaluates dense semantic retrieval (BAAI/bge-small-en-v1.5) and compares it with
sparse lexical retrieval (TF-IDF) across the evaluation query benchmark.
Measures:
- Latency (one-time model load, query embedding, vector retrieval, total warm latency)
- Catalog coverage
- Determinism
- Intra-list diversity
- TF-IDF vs Semantic vs Candidate Union characterization
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set

import numpy as np
import pandas as pd

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.recommendation.tfidf_model import TFIDFModel
from src.retrieval.embeddings import BGEEmbedder
from src.retrieval.hybrid import HybridCandidateRetriever
from src.retrieval.semantic import SemanticRetriever
from src.retrieval.tfidf import TFIDFRetriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("evaluate_semantic_retrieval")


def compute_dense_intra_list_diversity(
    recipe_ids: List[str],
    retriever: SemanticRetriever,
) -> float:
    """Calculate average pairwise cosine distance (1 - dot_product) among retrieved items."""
    if len(recipe_ids) < 2 or not retriever.is_ready or retriever.embeddings is None:
        return 1.0

    indices = [retriever.recipe_to_row[r] for r in recipe_ids if r in retriever.recipe_to_row]
    if len(indices) < 2:
        return 1.0

    vecs = retriever.embeddings[indices]  # (K, D) normalized
    # Pairwise cosine similarities via dot product: (K, K)
    sim_matrix = np.dot(vecs, vecs.T)
    k = len(indices)
    triu_idx = np.triu_indices(k, k=1)
    pairwise_sims = sim_matrix[triu_idx]

    avg_sim = float(np.mean(pairwise_sims)) if len(pairwise_sims) > 0 else 0.0
    diversity = 1.0 - avg_sim
    return float(np.clip(diversity, 0.0, 1.0))


def run_evaluation(
    queries_path: Path,
    embeddings_path: Path,
    index_path: Path,
    metadata_path: Path,
    top_k: int = 10,
    candidate_k: int = 50,
) -> Dict[str, Any]:
    """Run comprehensive retrieval evaluation suite."""
    print("=" * 80)
    print("KITCHENPILOT-V1: STAGE D SEMANTIC RETRIEVAL EVALUATION")
    print("=" * 80)

    # 1. Load evaluation query set
    if not queries_path.is_file():
        raise FileNotFoundError(f"Evaluation queries file missing at {queries_path}")
    with open(queries_path, "r", encoding="utf-8") as f:
        query_data = json.load(f)
    queries = query_data.get("queries", [])
    print(f"Loaded {len(queries)} evaluation benchmark queries from {queries_path.name}")

    # 2. Measure Model Loading Latency Separately
    print("\n[Phase 1] Model Loading Latency Measurement...")
    t_embedder_start = time.perf_counter()
    embedder = BGEEmbedder()
    embedder.load_model()
    t_model_load_sec = time.perf_counter() - t_embedder_start

    t_retriever_start = time.perf_counter()
    semantic_retriever = SemanticRetriever(
        embeddings_path=embeddings_path,
        index_path=index_path,
        metadata_path=metadata_path,
        embedder=embedder,
    )
    semantic_retriever.load_artifacts()
    t_retriever_load_sec = time.perf_counter() - t_retriever_start

    print(f" - BGE Model Load Time:      {t_model_load_sec:.3f} s")
    print(f" - Semantic Artifacts Load:   {t_retriever_load_sec:.3f} s")
    print(f" - Total Initialization:     {(t_model_load_sec + t_retriever_load_sec):.3f} s")

    # 3. Load TF-IDF Retriever
    print("\n[Phase 2] TF-IDF Initialization...")
    tfidf_model = TFIDFModel()
    tfidf_model.load_artifacts()
    tfidf_retriever = TFIDFRetriever(tfidf_model)
    print(f" - TF-IDF Matrix Shape:      {tfidf_model.tfidf_matrix.shape}")

    # 4. Initialize Hybrid Retriever
    hybrid_retriever = HybridCandidateRetriever(
        tfidf_retriever=tfidf_retriever,
        semantic_retriever=semantic_retriever,
        default_tfidf_top_k=candidate_k,
        default_semantic_top_k=candidate_k,
    )

    catalog_size = len(semantic_retriever.recipe_ids)

    # 5. Measure Latencies across queries
    print("\n[Phase 3] Query Benchmarking (Latency, Coverage, Diversity)...")
    query_embed_latencies_ms: List[float] = []
    vector_retrieval_latencies_ms: List[float] = []
    total_warm_latencies_ms: List[float] = []

    tfidf_latencies_ms: List[float] = []
    hybrid_latencies_ms: List[float] = []

    semantic_retrieved_unique: Set[str] = set()
    tfidf_retrieved_unique: Set[str] = set()
    hybrid_retrieved_unique: Set[str] = set()

    semantic_diversities: List[float] = []

    jaccard_overlaps: List[float] = []
    candidate_pool_sizes: List[int] = []
    provenance_counts = {"tfidf_only": 0, "semantic_only": 0, "both": 0}

    # Warmup query
    embedder.encode_text("warmup query")

    # First query latency (includes initial BLAS/torch dispatch)
    q0_text = queries[0]["query"]
    t0_start = time.perf_counter()
    _ = semantic_retriever.retrieve(q0_text, top_k=top_k)
    first_query_latency_ms = (time.perf_counter() - t0_start) * 1000

    # Execute all queries
    for q_item in queries:
        q_text = q_item["query"]

        # Semantic timing components
        t_enc_start = time.perf_counter()
        q_vec = embedder.encode_text(q_text)
        t_enc = (time.perf_counter() - t_enc_start) * 1000
        query_embed_latencies_ms.append(t_enc)

        t_sim_start = time.perf_counter()
        scores = semantic_retriever.compute_similarity_scores(q_vec)
        sorted_indices = np.argsort(-scores)[:top_k]
        sem_top_rids = [semantic_retriever.row_to_recipe[int(i)] for i in sorted_indices]
        t_sim = (time.perf_counter() - t_sim_start) * 1000
        vector_retrieval_latencies_ms.append(t_sim)
        total_warm_latencies_ms.append(t_enc + t_sim)

        semantic_retrieved_unique.update(sem_top_rids)
        div = compute_dense_intra_list_diversity(sem_top_rids, semantic_retriever)
        semantic_diversities.append(div)

        # TF-IDF timing
        t_tf_start = time.perf_counter()
        tf_results = tfidf_retriever.retrieve(q_text, top_k=top_k)
        t_tf = (time.perf_counter() - t_tf_start) * 1000
        tfidf_latencies_ms.append(t_tf)
        tf_top_rids = [r.recipe_id for r in tf_results]
        tfidf_retrieved_unique.update(tf_top_rids)

        # Hybrid candidate retrieval (candidate_k pool)
        t_hyb_start = time.perf_counter()
        hybrid_candidates = hybrid_retriever.retrieve_candidates(
            query=q_text,
            tfidf_top_k=candidate_k,
            semantic_top_k=candidate_k,
            enable_semantic=True,
        )
        t_hyb = (time.perf_counter() - t_hyb_start) * 1000
        hybrid_latencies_ms.append(t_hyb)

        hyb_rids = [c.recipe_id for c in hybrid_candidates]
        hybrid_retrieved_unique.update(hyb_rids)
        candidate_pool_sizes.append(len(hybrid_candidates))

        for c in hybrid_candidates:
            if c.provenance == "both":
                provenance_counts["both"] += 1
            elif c.provenance == "tfidf":
                provenance_counts["tfidf_only"] += 1
            elif c.provenance == "semantic":
                provenance_counts["semantic_only"] += 1

        # Candidate overlap Jaccard
        set_sem = set(sem_top_rids)
        set_tf = set(tf_top_rids)
        union_size = len(set_sem | set_tf)
        jaccard = len(set_sem & set_tf) / union_size if union_size > 0 else 0.0
        jaccard_overlaps.append(jaccard)

    # 6. Verify Determinism
    print("\n[Phase 4] Determinism Verification...")
    is_deterministic = True
    for q_item in queries[:5]:
        q_text = q_item["query"]
        run1 = semantic_retriever.retrieve(q_text, top_k=10)
        run2 = semantic_retriever.retrieve(q_text, top_k=10)
        rids1 = [r.recipe_id for r in run1]
        rids2 = [r.recipe_id for r in run2]
        scores1 = [r.score for r in run1]
        scores2 = [r.score for r in run2]
        if rids1 != rids2 or scores1 != scores2:
            is_deterministic = False
            break

    print(f" - Semantic Retrieval Determinism: {'PASSED (Exact Match)' if is_deterministic else 'FAILED'}")

    # Summary Metrics
    results_summary: Dict[str, Any] = {
        "model_loading_time_sec": round(t_model_load_sec, 3),
        "first_query_latency_ms": round(first_query_latency_ms, 2),
        "mean_query_embedding_latency_ms": round(float(np.mean(query_embed_latencies_ms)), 2),
        "mean_vector_retrieval_latency_ms": round(float(np.mean(vector_retrieval_latencies_ms)), 2),
        "mean_total_warm_latency_ms": round(float(np.mean(total_warm_latencies_ms)), 2),
        "p95_total_warm_latency_ms": round(float(np.percentile(total_warm_latencies_ms, 95)), 2),
        "mean_tfidf_latency_ms": round(float(np.mean(tfidf_latencies_ms)), 2),
        "mean_hybrid_candidate_latency_ms": round(float(np.mean(hybrid_latencies_ms)), 2),
        "semantic_catalog_coverage_pct": round((len(semantic_retrieved_unique) / catalog_size) * 100, 2),
        "tfidf_catalog_coverage_pct": round((len(tfidf_retrieved_unique) / catalog_size) * 100, 2),
        "hybrid_catalog_coverage_pct": round((len(hybrid_retrieved_unique) / catalog_size) * 100, 2),
        "semantic_unique_recipes_retrieved": len(semantic_retrieved_unique),
        "tfidf_unique_recipes_retrieved": len(tfidf_retrieved_unique),
        "hybrid_unique_recipes_retrieved": len(hybrid_retrieved_unique),
        "mean_semantic_diversity": round(float(np.mean(semantic_diversities)), 4),
        "mean_top10_jaccard_overlap": round(float(np.mean(jaccard_overlaps)), 4),
        "mean_candidate_pool_size": round(float(np.mean(candidate_pool_sizes)), 1),
        "provenance_summary": provenance_counts,
        "is_deterministic": is_deterministic,
        "num_queries_evaluated": len(queries),
        "catalog_size": catalog_size,
    }

    # Print Report
    print("\n" + "=" * 80)
    print("STAGE D EVALUATION SUMMARY REPORT")
    print("=" * 80)
    print(f"{'Metric':<40} | {'Value'}")
    print("-" * 80)
    print(f"{'BGE Model Load Time':<40} | {results_summary['model_loading_time_sec']} s")
    print(f"{'First Query Latency':<40} | {results_summary['first_query_latency_ms']} ms")
    print(f"{'Query Embedding Latency (Mean)':<40} | {results_summary['mean_query_embedding_latency_ms']} ms")
    print(f"{'Vector Similarity Latency (Mean)':<40} | {results_summary['mean_vector_retrieval_latency_ms']} ms")
    print(f"{'Total Warm Query Latency (Mean)':<40} | {results_summary['mean_total_warm_latency_ms']} ms")
    print(f"{'Total Warm Query Latency (P95)':<40} | {results_summary['p95_total_warm_latency_ms']} ms")
    print(f"{'TF-IDF Query Latency (Mean)':<40} | {results_summary['mean_tfidf_latency_ms']} ms")
    print(f"{'Hybrid Candidate Retrieval (Mean)':<40} | {results_summary['mean_hybrid_candidate_latency_ms']} ms")
    print("-" * 80)
    print(f"{'Catalog Size':<40} | {catalog_size} recipes")
    print(f"{'Semantic Coverage (25 queries, top-10)':<40} | {results_summary['semantic_unique_recipes_retrieved']} recipes ({results_summary['semantic_catalog_coverage_pct']}%)")
    print(f"{'TF-IDF Coverage (25 queries, top-10)':<40} | {results_summary['tfidf_unique_recipes_retrieved']} recipes ({results_summary['tfidf_catalog_coverage_pct']}%)")
    print(f"{'Hybrid Pool Coverage (top-50 pool)':<40} | {results_summary['hybrid_unique_recipes_retrieved']} recipes ({results_summary['hybrid_catalog_coverage_pct']}%)")
    print(f"{'Mean Top-10 Jaccard Overlap (TF vs BGE)':<40} | {results_summary['mean_top10_jaccard_overlap']}")
    print(f"{'Mean Candidate Pool Size (top-50 + top-50)':<40} | {results_summary['mean_candidate_pool_size']} recipes")
    print(f"{'Candidate Provenance: Both TFIDF & BGE':<40} | {provenance_counts['both']}")
    print(f"{'Candidate Provenance: TF-IDF Only':<40} | {provenance_counts['tfidf_only']}")
    print(f"{'Candidate Provenance: BGE Only':<40} | {provenance_counts['semantic_only']}")
    print(f"{'Mean Intra-list Diversity (BGE)':<40} | {results_summary['mean_semantic_diversity']}")
    print(f"{'Retrieval Determinism':<40} | {is_deterministic}")
    print("=" * 80)

    # Save output to docs/SEMANTIC_RETRIEVAL_EVALUATION.json
    eval_json_path = PROJECT_ROOT / "docs" / "SEMANTIC_RETRIEVAL_EVALUATION.json"
    eval_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(eval_json_path, "w", encoding="utf-8") as f:
        json.dump(results_summary, f, indent=2)
    print(f"\nEvaluation summary saved to: {eval_json_path}")

    return results_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate semantic retrieval performance.")
    parser.add_argument(
        "--queries-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "semantic_queries.json",
        help="Path to evaluation queries JSON",
    )
    parser.add_argument(
        "--embeddings-path",
        type=Path,
        default=PROJECT_ROOT / "models" / "retrieval" / "semantic" / "recipe_embeddings.npy",
        help="Path to recipe embeddings matrix",
    )
    parser.add_argument(
        "--index-path",
        type=Path,
        default=PROJECT_ROOT / "models" / "retrieval" / "semantic" / "recipe_index.csv",
        help="Path to recipe index CSV",
    )
    parser.add_argument(
        "--metadata-path",
        type=Path,
        default=PROJECT_ROOT / "models" / "retrieval" / "semantic" / "metadata.json",
        help="Path to metadata JSON",
    )
    parser.add_argument("--top-k", type=int, default=10, help="Top-K for evaluation")
    parser.add_argument("--candidate-k", type=int, default=50, help="Candidate pool K")
    args = parser.parse_args()

    try:
        run_evaluation(
            queries_path=args.queries_path,
            embeddings_path=args.embeddings_path,
            index_path=args.index_path,
            metadata_path=args.metadata_path,
            top_k=args.top_k,
            candidate_k=args.candidate_k,
        )
        return 0
    except Exception as e:
        logger.exception("Evaluation failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
