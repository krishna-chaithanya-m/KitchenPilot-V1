"""Explainability Subsystem for Stage E Constraint Engine.

Generates explicit, transparent reasoning for why candidates were accepted
or rejected. Avoids vague justifications or unsupported safety claims.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.constraints.models import (
    ComplianceStatus,
    ConstraintEvaluation,
    PantryMatchMetrics,
)


def generate_constraint_explanation(
    passed: bool,
    hard_failures: List[str],
    soft_matches: List[str],
    dietary_results: Dict[str, ComplianceStatus],
    pantry_metrics: Optional[PantryMatchMetrics],
    nutrition_results: Dict[str, Any],
) -> str:
    """Generate concise, deterministic explanation for candidate admissibility."""
    # 1. Rejected Candidates
    if not passed:
        if not hard_failures:
            return "Excluded: Did not meet specified criteria."
        # Concatenate explicit hard failure reasons
        return "Rejected: " + "; ".join(hard_failures)

    # 2. Accepted Candidates
    reasons: List[str] = []

    # Dietary compliances confirmed
    for diet_name, status in dietary_results.items():
        if status == ComplianceStatus.COMPLIANT:
            reasons.append(f"Satisfies {diet_name} requirement")

    # Pantry coverage
    if pantry_metrics and pantry_metrics.recipe_total_count > 0:
        pct = int(round(pantry_metrics.coverage_ratio * 100))
        if pct > 0:
            reasons.append(f"{pct}% pantry ingredient match")

    # Soft matches
    for sm in soft_matches[:2]:
        reasons.append(sm.lower())

    # Nutritional compliance
    cal = nutrition_results.get("per_serving_calories")
    if cal is not None and cal > 0:
        reasons.append(f"{cal:.0f} kcal per serving")

    if not reasons:
        return "Satisfies all specified criteria."

    return "Eligible: " + "; ".join(reasons) + "."
