"""Offline Semantic Index Generation Script for KitchenPilot-V1.

Generates 384-dimensional dense semantic embeddings using BAAI/bge-small-en-v1.5
over the authoritative recipe corpus, strictly preserving recipe ID ordering.
Saves:
- models/retrieval/semantic/recipe_embeddings.npy
- models/retrieval/semantic/recipe_index.csv
- models/retrieval/semantic/metadata.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.retrieval.corpus import RecipeCorpus
from src.retrieval.embeddings import BGEEmbedder, DEFAULT_MODEL_NAME, EXPECTED_EMBEDDING_DIM

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("build_semantic_index")


def compute_file_sha256(filepath: Path) -> str:
    """Compute hex SHA256 checksum of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_semantic_index(
    recipes_path: Path,
    linked_ingredients_path: Path,
    output_dir: Path,
    model_name: str = DEFAULT_MODEL_NAME,
    batch_size: int = 64,
    device: str | None = None,
) -> Dict[str, Any]:
    """Execute end-to-end deterministic semantic embedding index build."""
    t0 = time.perf_counter()
    logger.info("=" * 60)
    logger.info("Starting Semantic Index Generation for KitchenPilot-V1")
    logger.info("Model: %s (Target Dim: %d)", model_name, EXPECTED_EMBEDDING_DIM)
    logger.info("Recipes path: %s", recipes_path)
    logger.info("Output dir: %s", output_dir)
    logger.info("=" * 60)

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load authoritative corpus
    logger.info("Step 1/5: Loading authoritative corpus...")
    corpus = RecipeCorpus(
        recipes_path=recipes_path,
        linked_ingredients_path=linked_ingredients_path,
    )
    recipe_count = len(corpus)
    logger.info("Loaded %d recipes deterministically sorted by recipe_id.", recipe_count)

    # 2. Initialize Embedder
    logger.info("Step 2/5: Initializing BGE embedding model...")
    embedder = BGEEmbedder(
        model_name=model_name,
        device=device,
        normalize_embeddings=True,
    )
    t_load_start = time.perf_counter()
    embedder.load_model()
    t_load = time.perf_counter() - t_load_start
    logger.info("Model loaded in %.2fs.", t_load)

    # 3. Generate Embeddings in batches
    logger.info("Step 3/5: Generating %d dense embeddings (batch_size=%d)...", recipe_count, batch_size)
    t_enc_start = time.perf_counter()
    embeddings = embedder.encode_batch(
        texts=corpus.recipe_texts,
        batch_size=batch_size,
        show_progress_bar=True,
    )
    t_enc = time.perf_counter() - t_enc_start
    logger.info("Encoded %d recipes in %.2fs (%.1f recipes/sec).", recipe_count, t_enc, recipe_count / max(0.001, t_enc))

    # Verify output shape and float dtype
    if embeddings.shape != (recipe_count, EXPECTED_EMBEDDING_DIM):
        raise ValueError(
            f"Embeddings shape mismatch: expected ({recipe_count}, {EXPECTED_EMBEDDING_DIM}), got {embeddings.shape}"
        )
    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype(np.float32)

    # Verify L2 normalization
    norms = np.linalg.norm(embeddings, axis=1)
    norm_diff = np.max(np.abs(norms - 1.0))
    if norm_diff > 1e-4:
        raise ValueError(f"Embeddings are not properly L2-normalized. Max deviation: {norm_diff}")
    logger.info("L2 normalization verified: max deviation from unit norm is %e.", norm_diff)

    # 4. Save Artifacts
    logger.info("Step 4/5: Persisting artifacts...")
    embeddings_file = output_dir / "recipe_embeddings.npy"
    index_file = output_dir / "recipe_index.csv"
    metadata_file = output_dir / "metadata.json"

    # Save embeddings matrix
    np.save(embeddings_file, embeddings)
    file_size_mb = embeddings_file.stat().st_size / (1024 * 1024)
    logger.info("Saved embeddings to %s (%.2f MB).", embeddings_file, file_size_mb)

    # Save recipe index
    index_df = pd.DataFrame({
        "row_index": list(range(recipe_count)),
        "recipe_id": corpus.recipe_ids,
    })
    index_df.to_csv(index_file, index=False)
    logger.info("Saved recipe index to %s (%d rows).", index_file, len(index_df))

    # Compute checksums
    embeddings_sha256 = compute_file_sha256(embeddings_file)
    recipes_sha256 = compute_file_sha256(recipes_path)

    # Build comprehensive metadata
    model_meta = embedder.get_metadata()
    metadata: Dict[str, Any] = {
        "model_name": model_name,
        "model_version": "1.5",
        "embedding_dimension": EXPECTED_EMBEDDING_DIM,
        "normalization": "l2",
        "normalize_embeddings": True,
        "similarity_metric": "cosine_similarity_via_dot_product",
        "corpus_version": "0.1.0",
        "recipe_count": recipe_count,
        "generation_timestamp": datetime.now(timezone.utc).isoformat(),
        "library_version": model_meta.get("sentence_transformers_version"),
        "torch_version": model_meta.get("torch_version"),
        "corpus_sha256": recipes_sha256,
        "embeddings_sha256": embeddings_sha256,
        "embeddings_shape": list(embeddings.shape),
        "embeddings_file_size_bytes": embeddings_file.stat().st_size,
    }

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Saved metadata to %s.", metadata_file)

    # 5. Verification
    logger.info("Step 5/5: Verifying saved artifacts...")
    reloaded_emb = np.load(embeddings_file)
    reloaded_idx = pd.read_csv(index_file)
    if reloaded_emb.shape != embeddings.shape:
        raise ValueError("Verification failed: reloaded matrix shape mismatch.")
    if len(reloaded_idx) != recipe_count:
        raise ValueError("Verification failed: reloaded index row count mismatch.")
    if reloaded_idx["recipe_id"].tolist() != corpus.recipe_ids:
        raise ValueError("Verification failed: recipe ID ordering altered.")

    total_time = time.perf_counter() - t0
    logger.info("=" * 60)
    logger.info("Semantic Index Build Complete in %.2fs!", total_time)
    logger.info("All artifacts successfully verified.")
    logger.info("=" * 60)

    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dense semantic index for KitchenPilot-V1.")
    parser.add_argument(
        "--recipes-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "recipes.csv",
        help="Path to authoritative recipes.csv",
    )
    parser.add_argument(
        "--linked-ingredients-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "recipe_ingredients_linked.csv",
        help="Path to recipe_ingredients_linked.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "models" / "retrieval" / "semantic",
        help="Output directory for semantic artifacts",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help="HuggingFace model identifier",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Inference batch size",
    )
    args = parser.parse_args()

    try:
        build_semantic_index(
            recipes_path=args.recipes_path,
            linked_ingredients_path=args.linked_ingredients_path,
            output_dir=args.output_dir,
            model_name=args.model_name,
            batch_size=args.batch_size,
        )
        return 0
    except Exception as e:
        logger.exception("Semantic index build failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
