"""Configuration for KitchenPilot-V1 Recommendation Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TFIDFConfig:
    """TF-IDF vectorizer configuration."""
    ngram_range: Tuple[int, int] = (1, 2)
    min_df: int = 2
    sublinear_tf: bool = True
    norm: str = "l2"
    max_features: int | None = None


@dataclass(frozen=True)
class HybridWeights:
    """Configurable weights for the hybrid ranking formula."""
    similarity: float = 0.40
    ingredient: float = 0.25
    nutrition: float = 0.20
    preference: float = 0.15

    def validate(self) -> None:
        """Validate that weights sum approximately to 1.0 and are non-negative."""
        total = self.similarity + self.ingredient + self.nutrition + self.preference
        if abs(total - 1.0) > 1e-4:
            raise ValueError(f"Hybrid weights must sum to 1.0, got {total}")
        for k, v in [
            ("similarity", self.similarity),
            ("ingredient", self.ingredient),
            ("nutrition", self.nutrition),
            ("preference", self.preference),
        ]:
            if v < 0.0 or v > 1.0:
                raise ValueError(f"Weight '{k}' must be in [0, 1], got {v}")


@dataclass
class RecommendationConfig:
    """Global configuration paths and defaults."""
    # Data paths
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "processed")
    models_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "models" / "recommendation")

    recipes_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "processed" / "recipes.csv")
    linked_ingredients_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "processed" / "recipe_ingredients_linked.csv"
    )
    ingredient_nutrition_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "processed" / "recipe_ingredient_nutrition.csv"
    )
    recipe_nutrition_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "processed" / "recipe_nutrition.csv"
    )
    ingredients_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "processed" / "ingredients.csv"
    )

    corpus_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "processed" / "recipe_corpus.csv"
    )
    tfidf_vectorizer_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "models" / "recommendation" / "tfidf_vectorizer.joblib"
    )
    tfidf_matrix_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "models" / "recommendation" / "recipe_tfidf_matrix.npz"
    )
    recipe_index_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "models" / "recommendation" / "recipe_index.csv"
    )
    recommendation_results_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "processed" / "recommendation_results.csv"
    )

    # Models and weights
    tfidf: TFIDFConfig = field(default_factory=TFIDFConfig)
    weights: HybridWeights = field(default_factory=HybridWeights)
    ingredient_repetition_weight: int = 3  # Repeat canonical ingredients in corpus text to prioritize them
