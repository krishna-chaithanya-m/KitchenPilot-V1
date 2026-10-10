"""Dense Embedding Manager for Semantic Retrieval using BAAI/bge-small-en-v1.5.

Handles model loading, deterministic batch inference, and L2 normalization.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

logger = logging.getLogger("kitchenpilot.retrieval.embeddings")

DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EXPECTED_EMBEDDING_DIM = 384
SUPPORTED_BACKENDS: Tuple[str, ...] = ("onnx", "torch")


class BGEEmbedder:
    """Manages dense semantic embedding inference using BAAI/bge-small-en-v1.5.

    Supports both lightweight ONNX Runtime inference and standard PyTorch/SentenceTransformers.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        device: Optional[str] = None,
        normalize_embeddings: bool = True,
        backend: str = "onnx",
        onnx_model_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.normalize_embeddings = normalize_embeddings
        self.embedding_dimension = EXPECTED_EMBEDDING_DIM

        if not backend or not isinstance(backend, str):
            raise ValueError(
                f"Invalid semantic inference backend: {backend!r}. "
                f"Supported backends are: {', '.join(repr(b) for b in SUPPORTED_BACKENDS)}."
            )
        clean_backend = backend.lower().strip()
        if clean_backend not in SUPPORTED_BACKENDS:
            raise ValueError(
                f"Unsupported semantic inference backend: '{backend}'. "
                f"Supported backends are: {', '.join(repr(b) for b in SUPPORTED_BACKENDS)}."
            )
        self.backend = clean_backend
        self.onnx_model_path = Path(onnx_model_path) if onnx_model_path else None
        self._model = None
        self._tokenizer = None
        self._active_backend: Optional[str] = None

    def _load_onnx_model(self) -> None:
        """Initialize ONNX Runtime inference session and tokenizer."""
        try:
            import onnxruntime as ort
        except ImportError as e:
            raise ImportError(
                "onnxruntime is required for ONNX semantic retrieval backend. "
                "Please install it with `pip install onnxruntime`."
            ) from e

        from transformers import AutoTokenizer

        logger.info("Loading semantic embedding model via ONNX: %s", self.model_name)
        model_file = self.onnx_model_path
        if model_file is None:
            from huggingface_hub import hf_hub_download
            model_file = Path(hf_hub_download(self.model_name, "onnx/model.onnx"))
        elif not model_file.is_file():
            raise FileNotFoundError(
                f"Configured ONNX model file does not exist: {model_file.name}"
            )

        # Optimize thread pool for low-resource containers (single-threaded CPU prevents thread starvation)
        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = 1
        sess_options.inter_op_num_threads = 1
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = ort.InferenceSession(
            str(model_file),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )

        # Warmup and verify output dimension
        warmup_vec = self._encode_text_onnx("warmup")
        dim = int(warmup_vec.shape[-1])
        if dim != self.embedding_dimension:
            logger.warning(
                "ONNX model dimension %d differs from expected %d", dim, self.embedding_dimension
            )
            self.embedding_dimension = dim

    def _load_torch_model(self) -> None:
        """Load SentenceTransformer PyTorch model into memory."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for semantic retrieval. "
                "Please install it with `pip install sentence-transformers`."
            ) from e

        logger.info("Loading semantic embedding model via PyTorch: %s", self.model_name)
        kwargs = {}
        if self.device:
            kwargs["device"] = self.device

        self._model = SentenceTransformer(self.model_name, **kwargs)
        test_emb = self._model.encode("warmup", normalize_embeddings=self.normalize_embeddings)
        dim = int(test_emb.shape[-1])
        if dim != self.embedding_dimension:
            logger.warning(
                "Model dimension %d differs from expected %d", dim, self.embedding_dimension
            )
            self.embedding_dimension = dim

    def load_model(self) -> None:
        """Load embedding model into memory using configured backend.

        Raises:
            RuntimeError: If model initialization fails for the selected backend.
            ValueError: If an unsupported backend is configured.
        """
        if self.is_loaded:
            return

        if self.backend == "onnx":
            try:
                self._load_onnx_model()
                self._active_backend = "onnx"
            except Exception as e:
                logger.error(
                    "ONNX runtime initialization failed for model '%s': %s",
                    self.model_name,
                    e,
                )
                raise RuntimeError(
                    f"Failed to initialize ONNX semantic inference engine for model '{self.model_name}'."
                ) from e
        elif self.backend == "torch":
            try:
                self._load_torch_model()
                self._active_backend = "torch"
            except Exception as e:
                logger.error(
                    "PyTorch runtime initialization failed for model '%s': %s",
                    self.model_name,
                    e,
                )
                raise RuntimeError(
                    f"Failed to initialize PyTorch semantic inference engine for model '{self.model_name}'."
                ) from e
        else:
            raise ValueError(
                f"Unsupported semantic inference backend: '{self.backend}'. "
                f"Supported backends are: {', '.join(repr(b) for b in SUPPORTED_BACKENDS)}."
            )

    @property
    def is_loaded(self) -> bool:
        """Check if model is currently loaded in memory."""
        return self._model is not None

    def _encode_text_onnx(self, clean_text: str) -> np.ndarray:
        """Encode text using ONNX session with CLS pooling and L2 normalization."""
        tokens = self._tokenizer(
            clean_text,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="np",
        )
        inputs = {
            k: v for k, v in tokens.items()
            if k in ["input_ids", "attention_mask", "token_type_ids"]
        }
        outputs = self._model.run(["last_hidden_state"], inputs)[0]
        # BGE uses CLS token pooling (index 0)
        cls_vec = outputs[:, 0, :][0]
        if self.normalize_embeddings:
            norm = np.linalg.norm(cls_vec)
            if norm > 0:
                cls_vec = cls_vec / norm
        return np.asarray(cls_vec, dtype=np.float32)

    def _encode_batch_onnx(self, texts: Sequence[str], batch_size: int = 64) -> np.ndarray:
        """Encode batch of texts using ONNX session with CLS pooling and L2 normalization."""
        clean_texts = [t.strip() if t else "" for t in texts]
        results = []
        for i in range(0, len(clean_texts), batch_size):
            batch = clean_texts[i : i + batch_size]
            tokens = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="np",
            )
            inputs = {
                k: v for k, v in tokens.items()
                if k in ["input_ids", "attention_mask", "token_type_ids"]
            }
            outputs = self._model.run(["last_hidden_state"], inputs)[0]
            cls_batch = outputs[:, 0, :]
            if self.normalize_embeddings:
                norms = np.linalg.norm(cls_batch, axis=1, keepdims=True)
                norms = np.where(norms == 0, 1.0, norms)
                cls_batch = cls_batch / norms
            results.append(cls_batch)
        if not results:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)
        return np.vstack(results).astype(np.float32)

    def encode_text(self, text: str) -> np.ndarray:
        """Encode a single text string into a 1D normalized float32 embedding vector."""
        if not self.is_loaded:
            self.load_model()

        clean_text = text.strip() if text else ""
        if self._active_backend == "onnx":
            return self._encode_text_onnx(clean_text)

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
        if not self.is_loaded:
            self.load_model()

        if self._active_backend == "onnx":
            return self._encode_batch_onnx(texts, batch_size=batch_size)

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
        meta: Dict[str, Any] = {
            "model_name": self.model_name,
            "embedding_dimension": self.embedding_dimension,
            "normalization": self.normalize_embeddings,
            "backend": self._active_backend or self.backend,
        }
        try:
            import sentence_transformers
            meta["sentence_transformers_version"] = sentence_transformers.__version__
        except ImportError:
            pass
        try:
            import torch
            meta["torch_version"] = torch.__version__
        except ImportError:
            pass
        try:
            import onnxruntime
            meta["onnxruntime_version"] = onnxruntime.__version__
        except ImportError:
            pass
        return meta
