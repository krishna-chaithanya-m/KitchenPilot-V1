"""Retrieval Subsystem for KitchenPilot-V1.

Provides sparse lexical (TF-IDF), dense semantic (BGE-small-en-v1.5),
and hybrid candidate retrieval layers.
"""

from src.retrieval.base import RetrievalResult, Retriever
from src.retrieval.corpus import RecipeCorpus, build_query_semantic_text, build_recipe_semantic_text
from src.retrieval.embeddings import BGEEmbedder
from src.retrieval.hybrid import HybridCandidate, HybridCandidateRetriever
from src.retrieval.semantic import SemanticRetriever
from src.retrieval.tfidf import TFIDFRetriever

__all__ = [
    "Retriever",
    "RetrievalResult",
    "RecipeCorpus",
    "build_recipe_semantic_text",
    "build_query_semantic_text",
    "BGEEmbedder",
    "SemanticRetriever",
    "TFIDFRetriever",
    "HybridCandidate",
    "HybridCandidateRetriever",
]
