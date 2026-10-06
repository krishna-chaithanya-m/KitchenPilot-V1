"""Developer CLI Tool for Querying Semantic Retrieval.

Allows manual inspection of BGE-small-en-v1.5 dense retrieval rankings and similarity scores.
Usage:
    python scripts/query_semantic_retrieval.py --query "vegetarian South Indian breakfast with lentils" --top-k 10
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from src.retrieval.embeddings import BGEEmbedder
from src.retrieval.semantic import SemanticRetriever


def main() -> int:
    parser = argparse.ArgumentParser(description="Query KitchenPilot semantic retrieval engine.")
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Natural language or ingredient query text",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of candidates to retrieve (default: 10)",
    )
    parser.add_argument(
        "--embeddings-path",
        type=Path,
        default=PROJECT_ROOT / "models" / "retrieval" / "semantic" / "recipe_embeddings.npy",
        help="Path to precomputed embeddings matrix",
    )
    parser.add_argument(
        "--index-path",
        type=Path,
        default=PROJECT_ROOT / "models" / "retrieval" / "semantic" / "recipe_index.csv",
        help="Path to recipe index CSV",
    )
    parser.add_argument(
        "--recipes-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "recipes.csv",
        help="Path to authoritative recipes CSV for title lookup",
    )
    args = parser.parse_args()

    # Load recipe titles for display
    recipe_titles = {}
    if args.recipes_path.is_file():
        recipes_df = pd.read_csv(args.recipes_path)
        for _, row in recipes_df.iterrows():
            rid = str(row["recipe_id"]).strip()
            name = str(row.get("recipe_name", "")).strip()
            recipe_titles[rid] = name

    # Initialize Retriever
    retriever = SemanticRetriever(
        embeddings_path=args.embeddings_path,
        index_path=args.index_path,
    )
    retriever.load_artifacts()

    # Warmup / query timing
    t0 = time.perf_counter()
    results = retriever.search(query=args.query, top_k=args.top_k)
    latency_ms = (time.perf_counter() - t0) * 1000

    print("=" * 80)
    print(f"KitchenPilot Semantic Retrieval Query: \"{args.query}\"")
    print(f"Retrieved: {len(results)} recipes in {latency_ms:.2f} ms")
    print("=" * 80)
    print(f"{'Rank':<6} | {'Recipe ID':<10} | {'Score':<8} | {'Recipe Name'}")
    print("-" * 80)

    for r in results:
        rid = r["recipe_id"]
        score = r["score"]
        rank = r["rank"]
        name = recipe_titles.get(rid, "Unknown")
        print(f"{rank:<6} | {rid:<10} | {score:<8.4f} | {name}")

    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
