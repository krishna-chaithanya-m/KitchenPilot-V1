"""Hybrid Candidate Retrieval for KitchenPilot-V1.

Combines TF-IDF lexical candidate retrieval and BGE dense semantic retrieval
via candidate union, deduplicating by recipe ID and preserving retrieval provenance.
Does NOT directly sum uncalibrated raw similarity scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from src.retrieval.base import RetrievalResult
from src.retrieval.semantic import SemanticRetriever
from src.retrieval.tfidf import TFIDFRetriever


@dataclass(frozen=True)
class HybridCandidate:
    """Represents a deduplicated candidate recipe from the hybrid retrieval pool."""

    recipe_id: str
    provenance: str  # 'tfidf', 'semantic', 'both'
    tfidf_score: Optional[float] = None
    tfidf_rank: Optional[int] = None
    semantic_score: Optional[float] = None
    semantic_rank: Optional[int] = None


class HybridCandidateRetriever:
    """Orchestrates candidate union across TF-IDF and Semantic retrieval channels."""

    def __init__(
        self,
        tfidf_retriever: TFIDFRetriever,
        semantic_retriever: Optional[SemanticRetriever] = None,
        default_tfidf_top_k: int = 50,
        default_semantic_top_k: int = 50,
    ) -> None:
        self.tfidf_retriever = tfidf_retriever
        self.semantic_retriever = semantic_retriever
        self.default_tfidf_top_k = default_tfidf_top_k
        self.default_semantic_top_k = default_semantic_top_k

    def retrieve_candidates(
        self,
        query: str,
        tfidf_top_k: Optional[int] = None,
        semantic_top_k: Optional[int] = None,
        enable_semantic: bool = True,
    ) -> List[HybridCandidate]:
        """Retrieve candidate union across active retrievers.

        - Preserves all TF-IDF candidates.
        - Adds non-duplicate Semantic candidates.
        - Records provenance: 'tfidf', 'semantic', or 'both'.
        """
        k_tfidf = tfidf_top_k if tfidf_top_k is not None else self.default_tfidf_top_k
        k_semantic = semantic_top_k if semantic_top_k is not None else self.default_semantic_top_k

        # 1. Retrieve TF-IDF Candidates
        tfidf_results: List[RetrievalResult] = []
        if self.tfidf_retriever.is_ready and k_tfidf > 0:
            tfidf_results = self.tfidf_retriever.retrieve(query=query, top_k=k_tfidf)

        # 2. Retrieve Semantic Candidates (if enabled and ready)
        semantic_results: List[RetrievalResult] = []
        if (
            enable_semantic
            and self.semantic_retriever is not None
            and self.semantic_retriever.is_ready
            and k_semantic > 0
        ):
            semantic_results = self.semantic_retriever.retrieve(query=query, top_k=k_semantic)

        # 3. Build candidate union with provenance
        candidates_map: Dict[str, Dict[str, Any]] = {}

        for r in tfidf_results:
            candidates_map[r.recipe_id] = {
                "recipe_id": r.recipe_id,
                "tfidf_score": r.score,
                "tfidf_rank": r.rank,
                "semantic_score": None,
                "semantic_rank": None,
                "provenance": "tfidf",
            }

        for r in semantic_results:
            if r.recipe_id in candidates_map:
                entry = candidates_map[r.recipe_id]
                entry["semantic_score"] = r.score
                entry["semantic_rank"] = r.rank
                entry["provenance"] = "both"
            else:
                candidates_map[r.recipe_id] = {
                    "recipe_id": r.recipe_id,
                    "tfidf_score": None,
                    "tfidf_rank": None,
                    "semantic_score": r.score,
                    "semantic_rank": r.rank,
                    "provenance": "semantic",
                }

        return [
            HybridCandidate(
                recipe_id=c["recipe_id"],
                provenance=c["provenance"],
                tfidf_score=c["tfidf_score"],
                tfidf_rank=c["tfidf_rank"],
                semantic_score=c["semantic_score"],
                semantic_rank=c["semantic_rank"],
            )
            for c in candidates_map.values()
        ]
