"""Dense Semantic Retriever for KitchenPilot-V1.

Performs vector similarity search over precomputed BGE embeddings.
Since vectors are L2-normalized, cosine similarity equals the vector dot product.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.retrieval.base import RetrievalResult, Retriever
from src.retrieval.embeddings import BGEEmbedder, EXPECTED_EMBEDDING_DIM

logger = logging.getLogger("kitchenpilot.retrieval.semantic")


class SemanticRetriever:
    """Manages dense semantic candidate retrieval using normalized recipe embeddings."""

    def __init__(
        self,
        embeddings_path: Path,
        index_path: Path,
        metadata_path: Optional[Path] = None,
        embedder: Optional[BGEEmbedder] = None,
    ) -> None:
        self.embeddings_path = Path(embeddings_path)
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path) if metadata_path else None
        self.embedder = embedder or BGEEmbedder()

        self.embeddings: Optional[np.ndarray] = None
        self.recipe_ids: List[str] = []
        self.recipe_to_row: Dict[str, int] = {}
        self.row_to_recipe: Dict[int, str] = {}
        self.metadata: Dict[str, Any] = {}
        self._is_ready: bool = False

    def load_artifacts(self) -> None:
        """Load and validate precomputed embedding matrix and recipe index."""
        if not self.embeddings_path.is_file():
            raise FileNotFoundError(
                f"Semantic embeddings matrix missing at: {self.embeddings_path}. "
                "Run `python scripts/build_semantic_index.py` first."
            )
        if not self.index_path.is_file():
            raise FileNotFoundError(
                f"Semantic recipe index missing at: {self.index_path}. "
                "Run `python scripts/build_semantic_index.py` first."
            )

        # 1. Load Embeddings
        matrix = np.load(self.embeddings_path)
        if not isinstance(matrix, np.ndarray):
            raise ValueError(f"Expected numpy ndarray at {self.embeddings_path}, got {type(matrix)}")

        if matrix.ndim != 2:
            raise ValueError(
                f"Embeddings matrix must be 2-dimensional (N, D), got shape {matrix.shape}"
            )

        if matrix.shape[1] != EXPECTED_EMBEDDING_DIM:
            raise ValueError(
                f"Embeddings dimension mismatch: expected {EXPECTED_EMBEDDING_DIM}, got {matrix.shape[1]}"
            )

        self.embeddings = np.asarray(matrix, dtype=np.float32)

        # 2. Load Recipe Index
        index_df = pd.read_csv(self.index_path)
        if "recipe_id" not in index_df.columns:
            raise ValueError(f"Recipe index at {self.index_path} missing 'recipe_id' column")

        self.recipe_ids = index_df["recipe_id"].astype(str).tolist()
        if len(self.recipe_ids) != self.embeddings.shape[0]:
            raise ValueError(
                f"Row count mismatch: index has {len(self.recipe_ids)} recipes, "
                f"but embedding matrix has {self.embeddings.shape[0]} rows"
            )

        self.recipe_to_row = {rid: idx for idx, rid in enumerate(self.recipe_ids)}
        self.row_to_recipe = {idx: rid for idx, rid in enumerate(self.recipe_ids)}

        # 3. Load Metadata if available
        if self.metadata_path and self.metadata_path.is_file():
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
            except Exception as e:
                logger.warning("Failed to parse metadata at %s: %s", self.metadata_path, e)

        self._is_ready = True
        logger.info(
            "SemanticRetriever initialized with %d recipes (embedding dim: %d)",
            len(self.recipe_ids),
            self.embeddings.shape[1],
        )

    @property
    def is_ready(self) -> bool:
        """Check if artifacts are loaded and retriever is ready."""
        return self._is_ready and self.embeddings is not None

    def get_recipe_vector(self, recipe_id: str) -> np.ndarray:
        """Retrieve precomputed normalized embedding vector for a recipe."""
        if not self.is_ready or self.embeddings is None:
            raise RuntimeError("SemanticRetriever artifacts are not loaded.")
        if recipe_id not in self.recipe_to_row:
            raise KeyError(f"Recipe ID '{recipe_id}' not found in semantic index.")
        row_idx = self.recipe_to_row[recipe_id]
        return self.embeddings[row_idx]

    def compute_similarity_scores(self, query_vector: np.ndarray) -> np.ndarray:
        """Compute cosine similarity across all recipes.

        Since both recipe vectors and the query vector are L2-normalized:
            cosine_similarity(query, recipe) == dot_product(recipe, query)
        Bounded in [-1.0, 1.0] and clipped to [0.0, 1.0] for retrieval scoring.
        """
        if not self.is_ready or self.embeddings is None:
            raise RuntimeError("SemanticRetriever artifacts are not loaded.")

        # Vectorized dot product over matrix: (N, D) @ (D,) -> (N,)
        sims = np.dot(self.embeddings, query_vector)
        # Ensure finite floats and clip to [0.0, 1.0] for ranking
        sims = np.nan_to_num(sims, nan=0.0, posinf=1.0, neginf=0.0)
        return np.clip(sims, 0.0, 1.0)

    def retrieve(self, query: str, top_k: int = 10) -> List[RetrievalResult]:
        """Retrieve top_k candidates for a query using the common Retriever protocol."""
        if not self.is_ready or self.embeddings is None:
            raise RuntimeError("SemanticRetriever artifacts are not loaded.")

        clean_query = query.strip() if query else ""
        if not clean_query:
            return []

        query_vec = self.embedder.encode_text(clean_query)
        scores = self.compute_similarity_scores(query_vec)

        sorted_indices = np.argsort(-scores)

        results: List[RetrievalResult] = []
        for rank_idx, idx in enumerate(sorted_indices[:top_k], 1):
            rid = self.row_to_recipe[int(idx)]
            score = float(scores[idx])
            results.append(
                RetrievalResult(
                    recipe_id=rid,
                    score=round(score, 4),
                    rank=rank_idx,
                    retrieval_method="semantic",
                )
            )

        return results

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Public semantic retrieval search interface matching Section 13 specification.

        Returns list of dicts: [{'recipe_id': '...', 'score': 0.82, 'rank': 1}]
        Internal embedding vectors are never exposed.
        """
        results = self.retrieve(query=query, top_k=top_k)
        return [
            {
                "recipe_id": r.recipe_id,
                "score": r.score,
                "rank": r.rank,
            }
            for r in results
        ]
