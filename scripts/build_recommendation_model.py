"""Build Script for KitchenPilot-V1 Recommendation Model.

Builds the recipe corpus, fits the TF-IDF vectorizer deterministically,
saves artifacts, and validates model integrity.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.recommendation.config import RecommendationConfig
from src.recommendation.corpus_builder import CorpusBuilder
from src.recommendation.tfidf_model import TFIDFModel


def build_recommendation_model() -> None:
    """Build corpus, fit TF-IDF, save and validate artifacts."""
    start_time = time.time()
    config = RecommendationConfig()

    print("=" * 60)
    print("KitchenPilot-V1: Building Recommendation Model Artifacts")
    print("=" * 60)

    # 1. Load canonical data
    print("\n[1/5] Loading canonical dataset files...")
    assert config.recipes_path.is_file(), f"Missing: {config.recipes_path}"
    assert config.linked_ingredients_path.is_file(), f"Missing: {config.linked_ingredients_path}"
    assert config.recipe_nutrition_path.is_file(), f"Missing: {config.recipe_nutrition_path}"
    assert config.ingredients_path.is_file(), f"Missing: {config.ingredients_path}"

    recipes_df = pd.read_csv(config.recipes_path)
    ingredients_df = pd.read_csv(config.ingredients_path)
    num_recipes = len(recipes_df)
    num_canonical_ings = len(ingredients_df)
    print(f"Loaded {num_recipes:,} recipes and {num_canonical_ings:,} canonical ingredients.")

    # 2. Build corpus
    print("\n[2/5] Building deterministic recipe corpus...")
    builder = CorpusBuilder(config)
    corpus_df = builder.build_corpus()
    corpus_path = builder.save_corpus(corpus_df)
    print(f"Saved recipe corpus to: {corpus_path} ({len(corpus_df):,} rows)")

    # 3. Fit TF-IDF model
    print("\n[3/5] Fitting deterministic TF-IDF vectorizer...")
    model = TFIDFModel(config)
    model.fit(corpus_df)
    vocab_size = len(model.vectorizer.vocabulary_)
    matrix_shape = model.tfidf_matrix.shape
    nnz = model.tfidf_matrix.nnz
    print(f"Fitted TF-IDF Vectorizer:")
    print(f"  Vocabulary size: {vocab_size:,} n-grams")
    print(f"  Matrix shape:    {matrix_shape[0]:,} rows x {matrix_shape[1]:,} columns")
    print(f"  Non-zero entries: {nnz:,} ({nnz / (matrix_shape[0] * matrix_shape[1]) * 100:.2f}% density)")

    # 4. Save artifacts
    print("\n[4/5] Saving recommendation model artifacts...")
    model.save_artifacts()
    print(f"  Vectorizer: {config.tfidf_vectorizer_path}")
    print(f"  Matrix:     {config.tfidf_matrix_path}")
    print(f"  Index:      {config.recipe_index_path}")

    # 5. Validate artifacts
    print("\n[5/5] Validating saved artifacts...")
    reloaded_model = TFIDFModel(config)
    reloaded_model.load_artifacts()

    assert len(reloaded_model.recipe_ids) == num_recipes, "Recipe ID count mismatch!"
    assert reloaded_model.tfidf_matrix.shape == matrix_shape, "Matrix shape mismatch!"
    assert len(reloaded_model.vectorizer.vocabulary_) == vocab_size, "Vocab size mismatch!"

    # Test query transformation
    sample_vec = reloaded_model.transform_text("paneer butter masala tomato onion")
    assert sample_vec.shape == (1, vocab_size), "Query transform dimension mismatch!"
    sims = reloaded_model.compute_similarity_scores(sample_vec)
    assert len(sims) == num_recipes, "Similarity dimension mismatch!"
    assert 0.0 <= np.max(sims) <= 1.0, "Similarity out of [0, 1] range!"

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("RECOMMENDATION MODEL BUILD SUCCESSFUL")
    print("=" * 60)
    print(f"Total Recipes Indexed:    {num_recipes:,}")
    print(f"Canonical Ingredients:   {num_canonical_ings:,}")
    print(f"TF-IDF Vocabulary:       {vocab_size:,} terms")
    print(f"TF-IDF Matrix Shape:     {matrix_shape}")
    print(f"Build Time:              {elapsed:.2f} seconds")
    print("=" * 60)


if __name__ == "__main__":
    build_recommendation_model()
