"""Domain data models and schemas for Stage E Constraint Engine.

Defines severity levels (HARD, SOFT, INFO), 3-state compliance (COMPLIANT,
NON_COMPLIANT, UNKNOWN), ingredient match types, constraint specifications,
and structured evaluation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Union


class ConstraintSeverity(str, Enum):
    """Classification of constraint severity."""
    HARD = "HARD"    # Non-negotiable exclusion filter (violation causes rejection)
    SOFT = "SOFT"    # Preference signal (adjusts score or rank)
    INFO = "INFO"    # Informational metadata for explanations


class ComplianceStatus(str, Enum):
    """3-state compliance for dietary and safety rules."""
    COMPLIANT = "COMPLIANT"          # Confirmed compliant by authoritative data/rules
    NON_COMPLIANT = "NON_COMPLIANT"  # Confirmed violation
    UNKNOWN = "UNKNOWN"              # Insufficient data to verify compliance


class MatchType(str, Enum):
    """Categorical match precision for ingredient resolution."""
    EXACT = "EXACT"                  # Direct exact match on canonical name
    CANONICAL = "CANONICAL"          # Matched canonical ingredient ID or name
    ALIAS = "ALIAS"                  # Matched curated synonym/alias in ontology
    NORMALIZED = "NORMALIZED"        # Matched after standard phrase normalization
    LEXICAL = "LEXICAL"              # Safe lexical substring fallback
    UNRESOLVED = "UNRESOLVED"        # Unknown ingredient phrase


@dataclass(frozen=True)
class IngredientMatchResult:
    """Detailed resolution record for an ingredient query."""
    query_ingredient: str
    canonical_ingredient_id: Optional[str] = None
    canonical_name: Optional[str] = None
    matched_recipe_ingredient: Optional[str] = None
    match_type: MatchType = MatchType.UNRESOLVED
    confidence: float = 0.0
    source: str = "none"


@dataclass
class DietaryConstraints:
    """Dietary rule constraints using tri-state semantics.

    None = unspecified (no filtering)
    True = strictly required (HARD exclusion of non-compliant recipes)
    False = explicitly non-required (permissive)
    """
    vegetarian: Optional[bool] = None
    vegan: Optional[bool] = None
    jain: Optional[bool] = None
    satvik: Optional[bool] = None


@dataclass
class AllergenConstraints:
    """Allergen exclusion constraints. All exclusions are HARD filters."""
    excluded_allergens: List[str] = field(default_factory=list)


@dataclass
class IngredientConstraints:
    """Ingredient inclusion, exclusion, and pantry availability constraints."""
    excluded_ingredients: List[str] = field(default_factory=list)     # HARD exclusion
    required_ingredients: List[str] = field(default_factory=list)     # HARD requirement
    preferred_ingredients: List[str] = field(default_factory=list)    # SOFT preference
    available_ingredients: List[str] = field(default_factory=list)    # Pantry items
    require_all_ingredients: bool = False                            # When True, coverage < 1.0 is HARD REJECT


@dataclass
class NutritionConstraints:
    """Nutritional boundary constraints. Active limits are HARD filters."""
    min_calories: Optional[float] = None
    max_calories: Optional[float] = None
    min_protein_g: Optional[float] = None
    max_protein_g: Optional[float] = None
    min_carbs_g: Optional[float] = None
    max_carbs_g: Optional[float] = None
    min_fat_g: Optional[float] = None
    max_fat_g: Optional[float] = None
    min_fiber_g: Optional[float] = None
    max_fiber_g: Optional[float] = None

    def has_constraints(self) -> bool:
        return any(
            v is not None
            for v in [
                self.min_calories,
                self.max_calories,
                self.min_protein_g,
                self.max_protein_g,
                self.min_carbs_g,
                self.max_carbs_g,
                self.min_fat_g,
                self.max_fat_g,
                self.min_fiber_g,
                self.max_fiber_g,
            ]
        )


@dataclass
class SoftPreferenceConstraints:
    """Soft preference criteria for scoring candidate relevance."""
    cuisine: Optional[Union[str, List[str]]] = None
    region: Optional[Union[str, List[str]]] = None
    meal_type: Optional[Union[str, List[str]]] = None
    category: Optional[Union[str, List[str]]] = None
    max_prep_time_min: Optional[float] = None
    max_total_time_min: Optional[float] = None


@dataclass
class ConstraintRequest:
    """Complete container for all request-level constraints."""
    dietary: DietaryConstraints = field(default_factory=DietaryConstraints)
    allergens: AllergenConstraints = field(default_factory=AllergenConstraints)
    ingredients: IngredientConstraints = field(default_factory=IngredientConstraints)
    nutrition: NutritionConstraints = field(default_factory=NutritionConstraints)
    preferences: SoftPreferenceConstraints = field(default_factory=SoftPreferenceConstraints)


@dataclass
class PantryMatchMetrics:
    """Quantitative metrics for pantry availability matching."""
    matched_count: int = 0
    recipe_total_count: int = 0
    coverage_ratio: float = 0.0
    matched_ingredients: List[str] = field(default_factory=list)
    missing_ingredients: List[str] = field(default_factory=list)


@dataclass
class ConstraintEvaluation:
    """Structured, explainable outcome of evaluating a candidate recipe."""
    recipe_id: str
    passed: bool
    hard_failures: List[str] = field(default_factory=list)
    soft_matches: List[str] = field(default_factory=list)
    unknown_constraints: List[str] = field(default_factory=list)
    pantry_metrics: Optional[PantryMatchMetrics] = None
    dietary_results: Dict[str, ComplianceStatus] = field(default_factory=dict)
    nutrition_results: Dict[str, Any] = field(default_factory=dict)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "passed": self.passed,
            "hard_failures": self.hard_failures,
            "soft_matches": self.soft_matches,
            "unknown_constraints": self.unknown_constraints,
            "pantry_metrics": {
                "matched_count": self.pantry_metrics.matched_count,
                "recipe_total_count": self.pantry_metrics.recipe_total_count,
                "coverage_ratio": round(self.pantry_metrics.coverage_ratio, 3),
                "matched_ingredients": self.pantry_metrics.matched_ingredients,
                "missing_ingredients": self.pantry_metrics.missing_ingredients[:5],
            } if self.pantry_metrics else None,
            "dietary_results": {k: v.value for k, v in self.dietary_results.items()},
            "nutrition_results": self.nutrition_results,
            "explanation": self.explanation,
        }
