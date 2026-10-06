"""Structured Zero-Result Diagnostics and Guidance Engine (Stage J).

Provides structured, safe diagnostics when hard dietary, allergen, ingredient,
or nutrition constraints eliminate all candidate recipes.
In accordance with Stage J safety principles:
- Hard constraints are NEVER silently relaxed.
- Constraints are NEVER automatically modified.
- Safe, transparent user-facing recommendations and recovery guidance are provided.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from src.constraints.models import ConstraintRequest


def build_zero_result_diagnostics(
    raw_diagnostics: Optional[Dict[str, Any]],
    constraint_request: Optional[ConstraintRequest] = None,
    total_pool_size: int = 0,
) -> Dict[str, Any]:
    """Construct structured zero-result diagnostics with safe recovery guidance.

    Distinguishes between:
    - dietary_conflict
    - allergen_conflict
    - insufficient_pantry_coverage
    - nutrition_constraint_conflict
    - incompatible_preference_combination
    - insufficient_eligible_recipes
    - unresolved_ingredient_constraints
    """
    diag = raw_diagnostics or {}
    total_candidates = diag.get("total_candidates", total_pool_size)
    dietary_rej = diag.get("dietary_rejections", 0)
    allergen_rej = diag.get("allergen_rejections", 0)
    exclusion_rej = diag.get("ingredient_exclusion_rejections", 0)
    nutrition_rej = diag.get("nutrition_rejections", 0)
    required_rej = diag.get("required_ingredient_rejections", 0)

    # Determine primary cause based on highest rejection counts and requested constraints
    primary_causes: List[str] = []
    guidance: List[str] = []
    suggestions: List[str] = []

    if total_candidates == 0:
        primary_causes.append("insufficient_eligible_recipes")
        guidance.append("No recipes matched the initial search query or candidate pool.")
        suggestions.append("Broaden your query keywords or search terms.")

    if allergen_rej > 0 and allergen_rej >= total_candidates * 0.5:
        primary_causes.append("allergen_conflict")
        guidance.append(
            f"Allergen filters eliminated {allergen_rej} recipes. Many candidates in this category contain excluded allergens."
        )
        suggestions.append(
            "Review excluded allergens to verify if certain cross-reactive categories can be refined."
        )

    if dietary_rej > 0 and (dietary_rej >= total_candidates * 0.5 or not primary_causes):
        primary_causes.append("dietary_conflict")
        guidance.append(
            f"Strict dietary lifestyle constraints eliminated {dietary_rej} candidate recipes."
        )
        suggestions.append(
            "If appropriate, check if multiple strict dietary flags (e.g. Vegan + Jain + Satvik) were simultaneously enabled."
        )

    if nutrition_rej > 0 and (nutrition_rej >= total_candidates * 0.5 or not primary_causes):
        primary_causes.append("nutrition_constraint_conflict")
        guidance.append(
            f"Macro-nutrient or calorie constraints eliminated {nutrition_rej} recipes."
        )
        suggestions.append(
            "Consider broadening maximum calorie, fat, or carb limits, or lowering minimum protein targets."
        )

    if (exclusion_rej > 0 or required_rej > 0) and (not primary_causes or (exclusion_rej + required_rej) >= total_candidates * 0.3):
        if exclusion_rej > 0:
            primary_causes.append("unresolved_ingredient_constraints")
            guidance.append(
                f"Excluded ingredients eliminated {exclusion_rej} candidate recipes."
            )
            suggestions.append(
                "Remove one or more excluded ingredients that may be staple components of this dish category."
            )
        if required_rej > 0:
            primary_causes.append("insufficient_pantry_coverage")
            guidance.append(
                f"Required ingredients or pantry constraints eliminated {required_rej} recipes."
            )
            suggestions.append(
                "Add additional available pantry ingredients or relax strict required-ingredient flags."
            )

    if not primary_causes:
        primary_causes.append("incompatible_preference_combination")
        guidance.append(
            "The combination of specified dietary, allergen, ingredient, and nutritional constraints left 0 matching recipes."
        )
        suggestions.append(
            "Broaden soft preferences such as cuisine or meal type, or adjust one constraint dimension at a time."
        )

    return {
        # Backward-compatible Stage E diagnostics keys
        "total_candidates": total_candidates,
        "eligible_count": diag.get("eligible_count", 0),
        "rejected_count": diag.get("rejected_count", total_candidates),
        "allergen_rejections": allergen_rej,
        "ingredient_exclusion_rejections": exclusion_rej,
        "dietary_rejections": dietary_rej,
        "nutrition_rejections": nutrition_rej,
        "required_ingredient_rejections": required_rej,
        # Stage J structured diagnostics & guidance
        "status": "zero_results",
        "primary_cause": primary_causes[0],
        "all_causes": primary_causes,
        "candidate_pool_size": total_candidates,
        "rejection_breakdown": {
            "dietary": dietary_rej,
            "allergens": allergen_rej,
            "ingredient_exclusions": exclusion_rej,
            "nutrition_limits": nutrition_rej,
            "required_ingredients": required_rej,
            "total_rejected": diag.get("rejected_count", total_candidates),
        },
        "guidance": guidance,
        "safe_suggestions": suggestions,
        "constraint_preservation_notice": (
            "Safety invariant: KitchenPilot-V1 preserves all hard constraints and never silently relaxes dietary, allergen, or safety filters."
        ),
    }

