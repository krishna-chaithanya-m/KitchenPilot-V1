"""KitchenPilot-V1 Recommendation Engine Package."""

from src.recommendation.config import HybridWeights, RecommendationConfig, TFIDFConfig
from src.recommendation.corpus_builder import CorpusBuilder
from src.recommendation.explainability import ExplanationGenerator
from src.recommendation.hybrid_ranker import HybridRanker, ScoredCandidate
from src.recommendation.ingredient_matcher import IngredientMatcher, IngredientMatchResult
from src.recommendation.nutrition_scorer import NutritionGoals, NutritionScorer, NutritionScoreResult
from src.recommendation.preference_filter import PreferenceFilter, UserPreferences
from src.recommendation.recommender import KitchenPilotRecommender
from src.recommendation.tfidf_model import TFIDFModel

__all__ = [
    "HybridWeights",
    "RecommendationConfig",
    "TFIDFConfig",
    "CorpusBuilder",
    "ExplanationGenerator",
    "HybridRanker",
    "ScoredCandidate",
    "IngredientMatcher",
    "IngredientMatchResult",
    "NutritionGoals",
    "NutritionScorer",
    "NutritionScoreResult",
    "PreferenceFilter",
    "UserPreferences",
    "KitchenPilotRecommender",
    "TFIDFModel",
]
