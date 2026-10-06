"""Common Retrieval Abstraction for KitchenPilot-V1.

Defines unified data models and protocol for candidate retrieval layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, runtime_checkable


@dataclass(frozen=True)
class RetrievalResult:
    """Represents a candidate recipe retrieved by a search mechanism."""

    recipe_id: str
    score: float
    rank: int
    retrieval_method: str  # e.g., 'tfidf', 'semantic', 'hybrid'


@runtime_checkable
class Retriever(Protocol):
    """Abstract interface protocol for candidate retrievers."""

    def retrieve(self, query: str, top_k: int = 10) -> List[RetrievalResult]:
        """Retrieve top_k candidates matching the query."""
        ...
