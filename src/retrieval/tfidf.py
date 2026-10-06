"""TF-IDF Retriever Adapter for KitchenPilot-V1.

Wraps the existing TFIDFModel to conform to the common Retriever protocol,
preserving exact V1 lexical retrieval behavior.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

from src.recommendation.tfidf_model import TFIDFModel
from src.retrieval.base import RetrievalResult, Retriever

logger = logging.getLogger("kitchenpilot.retrieval.tfidf")


class TFIDFRetriever:
    """Adapts existing TFIDFModel to the standard Retriever interface."""

    def __init__(self, tfidf_model: TFIDFModel) -> None:
        self.model = tfidf_model

    @property
    def is_ready(self) -> bool:
        """Check if underlying TFIDF model is fitted/loaded."""
        return self.model.tfidf_matrix is not None and self.model.vectorizer is not None

    def retrieve(self, query: str, top_k: int = 10) -> List[RetrievalResult]:
        """Retrieve top_k candidates for a text query using sparse TF-IDF cosine similarity."""
        if not self.is_ready:
            raise RuntimeError("TFIDFRetriever is not ready. Artifacts must be loaded first.")

        clean_query = query.strip() if query else ""
        if not clean_query:
            return []

        # Vectorize query
        query_vec = self.model.transform_text(clean_query)
        scores = self.model.compute_similarity_scores(query_vec)

        sorted_indices = np.argsort(-scores)

        results: List[RetrievalResult] = []
        for rank_idx, idx in enumerate(sorted_indices[:top_k], 1):
            rid = self.model.row_to_recipe[int(idx)]
            score = float(scores[idx])
            results.append(
                RetrievalResult(
                    recipe_id=rid,
                    score=round(score, 4),
                    rank=rank_idx,
                    retrieval_method="tfidf",
                )
            )

        return results
