"""Production Constraint Engine for KitchenPilot-V1.

Orchestrates multi-stage candidate validation:
1. Request Conflict Validation
2. Allergen Hard Exclusions
3. Ingredient Hard Exclusions
4. Dietary Hard Rules (Vegetarian, Vegan, Jain, Satvik)
5. Nutrition Hard Boundaries
6. Required Ingredients & Pantry Strict Availability
7. Soft Preference Scoring Signals & Deterministic Explanations
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.constraints.dietary import DietaryRuleEngine
from src.constraints.explanations import generate_constraint_explanation
from src.constraints.ingredients import IngredientConstraintMatcher
from src.constraints.models import (
    ConstraintEvaluation,
    ConstraintRequest,
    PantryMatchMetrics,
)
from src.constraints.nutrition import NutritionConstraintEvaluator

logger = logging.getLogger("kitchenpilot.constraints.engine")


class ConstraintEngine:
    """Production constraint and ingredient matching orchestrator."""

    def __init__(
        self,
        ingredient_matcher: Optional[IngredientConstraintMatcher] = None,
        dietary_engine: Optional[DietaryRuleEngine] = None,
        nutrition_evaluator: Optional[NutritionConstraintEvaluator] = None,
    ) -> None:
        self.ingredient_matcher = ingredient_matcher or IngredientConstraintMatcher()
        self.dietary_engine = dietary_engine or DietaryRuleEngine(self.ingredient_matcher)
        self.nutrition_evaluator = nutrition_evaluator or NutritionConstraintEvaluator()

    def validate_request(self, request: ConstraintRequest) -> List[str]:
        """Validate constraint request for logical contradictions and conflicts."""
        return self.dietary_engine.detect_constraint_conflicts(
            dietary=request.dietary,
            required_ingredients=request.ingredients.required_ingredients,
            excluded_allergens=request.allergens.excluded_allergens,
        )

    def evaluate_candidate(
        self,
        recipe_id: str,
        request: ConstraintRequest,
    ) -> ConstraintEvaluation:
        """Evaluate a single candidate recipe against all request-level constraints.

        Strict execution order:
        1. Allergen Hard Exclusions
        2. Ingredient Hard Exclusions
        3. Dietary Hard Rules
        4. Nutrition Hard Limits
        5. Required Ingredient Checks & Strict Pantry Mode
        6. Soft Matches & Deterministic Explanations
        """
        hard_failures: List[str] = []
        soft_matches: List[str] = []
        unknown_constraints: List[str] = []

        # 1. Allergen Hard Filters
        allergen_pass, allergen_fails, _ = self.dietary_engine.evaluate_allergen_exclusions(
            recipe_id=recipe_id,
            allergens=request.allergens,
        )
        hard_failures.extend(allergen_fails)

        # 2. Ingredient Constraints (Exclusions, Requirements, Pantry)
        ing_pass, ing_fails, ing_soft, pantry_metrics = (
            self.ingredient_matcher.evaluate_ingredient_constraints(
                recipe_id=recipe_id,
                constraints=request.ingredients,
            )
        )
        hard_failures.extend(ing_fails)
        soft_matches.extend(ing_soft)

        # 3. Dietary Hard Rules (3-state compliance)
        diet_pass, diet_fails, diet_statuses = self.dietary_engine.evaluate_dietary_compliance(
            recipe_id=recipe_id,
            constraints=request.dietary,
        )
        hard_failures.extend(diet_fails)

        # 4. Nutrition Hard Limits
        nut_pass, nut_fails, nut_unknowns, nut_summary = (
            self.nutrition_evaluator.evaluate_nutrition_constraints(
                recipe_id=recipe_id,
                constraints=request.nutrition,
            )
        )
        hard_failures.extend(nut_fails)
        unknown_constraints.extend(nut_unknowns)

        # Overall Admissibility: must pass ALL hard filters
        passed = len(hard_failures) == 0

        # Generate Explainability
        explanation = generate_constraint_explanation(
            passed=passed,
            hard_failures=hard_failures,
            soft_matches=soft_matches,
            dietary_results=diet_statuses,
            pantry_metrics=pantry_metrics,
            nutrition_results=nut_summary,
        )

        return ConstraintEvaluation(
            recipe_id=recipe_id,
            passed=passed,
            hard_failures=hard_failures,
            soft_matches=soft_matches,
            unknown_constraints=unknown_constraints,
            pantry_metrics=pantry_metrics,
            dietary_results=diet_statuses,
            nutrition_results=nut_summary,
            explanation=explanation,
        )

    def filter_candidates(
        self,
        candidate_recipe_ids: Sequence[str],
        request: ConstraintRequest,
    ) -> Tuple[List[str], Dict[str, ConstraintEvaluation], Dict[str, int]]:
        """Filter a list of candidate recipe IDs through the constraint engine.

        Returns:
            (eligible_recipe_ids, evaluation_map, rejection_summary_diagnostics)
        """
        eligible: List[str] = []
        evaluations: Dict[str, ConstraintEvaluation] = {}
        diagnostics = {
            "total_candidates": len(candidate_recipe_ids),
            "eligible_count": 0,
            "rejected_count": 0,
            "allergen_rejections": 0,
            "ingredient_exclusion_rejections": 0,
            "dietary_rejections": 0,
            "nutrition_rejections": 0,
            "required_ingredient_rejections": 0,
        }

        for rid in candidate_recipe_ids:
            ev = self.evaluate_candidate(rid, request)
            evaluations[rid] = ev
            if ev.passed:
                eligible.append(rid)
            else:
                diagnostics["rejected_count"] += 1
                for f in ev.hard_failures:
                    f_low = f.lower()
                    if "allergen" in f_low:
                        diagnostics["allergen_rejections"] += 1
                    elif "excluded ingredient" in f_low:
                        diagnostics["ingredient_exclusion_rejections"] += 1
                    elif "dietary" in f_low or "vegetarian" in f_low or "vegan" in f_low or "jain" in f_low or "satvik" in f_low:
                        diagnostics["dietary_rejections"] += 1
                    elif "calories" in f_low or "protein" in f_low or "carbohydrates" in f_low or "fat" in f_low or "fiber" in f_low or "nutrition" in f_low:
                        diagnostics["nutrition_rejections"] += 1
                    elif "missing required" in f_low or "pantry" in f_low:
                        diagnostics["required_ingredient_rejections"] += 1

        diagnostics["eligible_count"] = len(eligible)
        return eligible, evaluations, diagnostics
