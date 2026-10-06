"""Production Constraint & Ingredient Matching Engine for KitchenPilot-V1.

Sits strictly between candidate retrieval and final ranking. Provides
deterministic hard constraint filtering, allergen exclusions, dietary compliance,
ingredient availability/pantry matching, nutritional boundary checking, and
human-readable explainability.
"""

from src.constraints.dietary import DietaryRuleEngine
from src.constraints.engine import ConstraintEngine
from src.constraints.explanations import generate_constraint_explanation
from src.constraints.ingredients import IngredientConstraintMatcher
from src.constraints.models import (
    AllergenConstraints,
    ComplianceStatus,
    ConstraintEvaluation,
    ConstraintRequest,
    ConstraintSeverity,
    DietaryConstraints,
    IngredientConstraints,
    IngredientMatchResult,
    MatchType,
    NutritionConstraints,
    PantryMatchMetrics,
    SoftPreferenceConstraints,
)
from src.constraints.diagnostics import build_zero_result_diagnostics
from src.constraints.nutrition import NutritionConstraintEvaluator

__all__ = [
    "AllergenConstraints",
    "ComplianceStatus",
    "ConstraintEngine",
    "ConstraintEvaluation",
    "ConstraintRequest",
    "ConstraintSeverity",
    "DietaryConstraints",
    "DietaryRuleEngine",
    "IngredientConstraintMatcher",
    "IngredientConstraints",
    "IngredientMatchResult",
    "MatchType",
    "NutritionConstraintEvaluator",
    "NutritionConstraints",
    "PantryMatchMetrics",
    "SoftPreferenceConstraints",
    "generate_constraint_explanation",
    "build_zero_result_diagnostics",
]

