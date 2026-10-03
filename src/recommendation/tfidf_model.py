"""TF-IDF Model and Similarity Engine for KitchenPilot-V1.

Implements deterministic TF-IDF feature extraction, artifact persistence,
and query/recipe-level cosine similarity calculation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.recommendation.config import RecommendationConfig


class TFIDFModel:
    """Manages TF-IDF representation and similarity calculation across recipes."""

    def __init__(self, config: Optional[RecommendationConfig] = None) -> None:
        self.config = config or RecommendationConfig()
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix: Optional[sp.csr_matrix] = None
        self.recipe_ids: List[str] = []
        self.recipe_to_row: Dict[str, int] = {}
        self.row_to_recipe: Dict[int, str] = {}

    def fit(self, corpus_df: pd.DataFrame) -> None:
        """Fit TF-IDF model deterministically on the recipe corpus."""
        # Ensure deterministic ordering by recipe_id
        corpus_df = corpus_df.sort_values(by="recipe_id", ascending=True).reset_index(drop=True)
        self.recipe_ids = corpus_df["recipe_id"].astype(str).tolist()
        self.recipe_to_row = {rid: idx for idx, rid in enumerate(self.recipe_ids)}
        self.row_to_recipe = {idx: rid for idx, rid in enumerate(self.recipe_ids)}

        cfg = self.config.tfidf
        self.vectorizer = TfidfVectorizer(
            ngram_range=cfg.ngram_range,
            min_df=cfg.min_df,
            sublinear_tf=cfg.sublinear_tf,
            norm=cfg.norm,
            max_features=cfg.max_features,
        )

        texts = corpus_df["corpus_text"].fillna("").astype(str).tolist()
        matrix = self.vectorizer.fit_transform(texts)
        self.tfidf_matrix = sp.csr_matrix(matrix)

    def save_artifacts(self) -> None:
        """Save fitted vectorizer, sparse TF-IDF matrix, and recipe index."""
        if self.vectorizer is None or self.tfidf_matrix is None:
            raise ValueError("Model must be fitted before saving artifacts.")

        self.config.models_dir.mkdir(parents=True, exist_ok=True)

        # 1. Vectorizer
        joblib.dump(self.vectorizer, self.config.tfidf_vectorizer_path)

        # 2. TF-IDF Matrix
        sp.save_npz(self.config.tfidf_matrix_path, self.tfidf_matrix)

        # 3. Recipe Index
        index_df = pd.DataFrame({
            "row_index": list(range(len(self.recipe_ids))),
            "recipe_id": self.recipe_ids,
        })
        index_df.to_csv(self.config.recipe_index_path, index=False)

    def load_artifacts(self) -> None:
        """Load saved artifacts from disk."""
        if not self.config.tfidf_vectorizer_path.is_file():
            raise FileNotFoundError(f"Missing vectorizer: {self.config.tfidf_vectorizer_path}")
        if not self.config.tfidf_matrix_path.is_file():
            raise FileNotFoundError(f"Missing TF-IDF matrix: {self.config.tfidf_matrix_path}")
        if not self.config.recipe_index_path.is_file():
            raise FileNotFoundError(f"Missing recipe index: {self.config.recipe_index_path}")

        self.vectorizer = joblib.load(self.config.tfidf_vectorizer_path)
        self.tfidf_matrix = sp.load_npz(self.config.tfidf_matrix_path).tocsr()

        index_df = pd.read_csv(self.config.recipe_index_path)
        self.recipe_ids = index_df["recipe_id"].astype(str).tolist()
        self.recipe_to_row = {rid: int(idx) for idx, rid in zip(index_df["row_index"], self.recipe_ids)}
        self.row_to_recipe = {int(idx): rid for idx, rid in zip(index_df["row_index"], self.recipe_ids)}

    def get_recipe_vector(self, recipe_id: str) -> sp.csr_matrix:
        """Get the sparse 1xV TF-IDF vector for a specific recipe."""
        if self.tfidf_matrix is None:
            raise ValueError("Model not loaded or fitted.")
        if recipe_id not in self.recipe_to_row:
            raise KeyError(f"Recipe ID '{recipe_id}' not found in index.")
        row_idx = self.recipe_to_row[recipe_id]
        return self.tfidf_matrix[row_idx : row_idx + 1]

    def transform_text(self, text: str) -> sp.csr_matrix:
        """Transform arbitrary query text into a sparse 1xV TF-IDF vector."""
        if self.vectorizer is None:
            raise ValueError("Model not loaded or fitted.")
        return self.vectorizer.transform([text])

    def compute_similarity_scores(self, query_vector: sp.csr_matrix) -> np.ndarray:
        """Compute 1D array of cosine similarities against all recipes in corpus."""
        if self.tfidf_matrix is None:
            raise ValueError("Model not loaded or fitted.")
        # cosine_similarity returns shape (1, N)
        sims = cosine_similarity(query_vector, self.tfidf_matrix).flatten()
        # Bound strictly in [0.0, 1.0]
        return np.clip(sims, 0.0, 1.0)

    def recommend_similar_recipes(
        self,
        recipe_id: str,
        top_k: int = 10,
        exclude_self: bool = True,
    ) -> List[Tuple[str, float]]:
        """Return top_k similar recipes based purely on TF-IDF cosine similarity."""
        if recipe_id not in self.recipe_to_row:
            raise KeyError(f"Recipe ID '{recipe_id}' not found in index.")

        query_vec = self.get_recipe_vector(recipe_id)
        scores = self.compute_similarity_scores(query_vec)

        # Get sorted indices descending
        sorted_indices = np.argsort(-scores)

        results: List[Tuple[str, float]] = []
        for idx in sorted_indices:
            target_id = self.row_to_recipe[int(idx)]
            if exclude_self and target_id == recipe_id:
                continue
            results.append((target_id, float(scores[idx])))
            if len(results) >= top_k:
                break

        return results
