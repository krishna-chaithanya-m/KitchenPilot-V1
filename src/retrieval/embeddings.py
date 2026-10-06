"""Dense Embedding Manager for Semantic Retrieval using BAAI/bge-small-en-v1.5.

Handles model loading, deterministic batch inference, and L2 normalization.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np

logger = logging.getLogger("kitchenpilot.retrieval.embeddings")

DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EXPECTED_EMBEDDING_DIM = 384


class BGEEmbedder:
    """Manages dense semantic embedding inference using BAAI/bge-small-en-v1.5."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        device: Optional[str] = None,
        normalize_embeddings: bool = True,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.normalize_embeddings = normalize_embeddings
        self.embedding_dimension = EXPECTED_EMBEDDING_DIM
        self._model = None

    def load_model(self) -> None:
        """Load SentenceTransformer model into memory."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for semantic retrieval. "
                "Please install it with `pip install sentence-transformers`."
            ) from e

        logger.info("Loading semantic embedding model: %s", self.model_name)
        kwargs = {}
        if self.device:
            kwargs["device"] = self.device

        self._model = SentenceTransformer(self.model_name, **kwargs)
        # Verify dimension
        test_emb = self._model.encode("warmup", normalize_embeddings=self.normalize_embeddings)
        dim = int(test_emb.shape[-1])
        if dim != self.embedding_dimension:
            logger.warning(
                "Model dimension %d differs from expected %d", dim, self.embedding_dimension
            )
            self.embedding_dimension = dim

    @property
    def is_loaded(self) -> bool:
        """Check if model is currently loaded in memory."""
        return self._model is not None

    def encode_text(self, text: str) -> np.ndarray:
        """Encode a single text string into a 1D normalized float32 embedding vector."""
        if self._model is None:
            self.load_model()

        clean_text = text.strip() if text else ""
        emb = self._model.encode(
            clean_text,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return np.asarray(emb, dtype=np.float32)

    def encode_batch(
        self,
        texts: Sequence[str],
        batch_size: int = 64,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        """Encode a sequence of texts into a 2D (N, D) normalized float32 matrix."""
        if self._model is None:
            self.load_model()

        clean_texts = [t.strip() if t else "" for t in texts]
        embeddings = self._model.encode(
            clean_texts,
            batch_size=batch_size,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=show_progress_bar,
            convert_to_numpy=True,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def get_metadata(self) -> Dict[str, Any]:
        """Return embedding model configuration and metadata."""
        import sentence_transformers
        import torch

        return {
            "model_name": self.model_name,
            "embedding_dimension": self.embedding_dimension,
            "normalization": self.normalize_embeddings,
            "sentence_transformers_version": sentence_transformers.__version__,
            "torch_version": torch.__version__,
        }
