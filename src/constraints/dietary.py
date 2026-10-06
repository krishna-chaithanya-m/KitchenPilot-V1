"""Dietary and Allergen Rule Engine for KitchenPilot-V1.

Implements 3-state compliance (COMPLIANT, NON_COMPLIANT, UNKNOWN) for
Vegetarian, Vegan, Jain, and Satvik rules, hard allergen exclusions,
and impossible constraint conflict detection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from src.constraints.ingredients import IngredientConstraintMatcher
from src.constraints.models import (
    AllergenConstraints,
    ComplianceStatus,
    DietaryConstraints,
)
from src.ingredients.ontology import (
    ALLERGEN_CATEGORY_MAP,
    ALLERGEN_NAME_RULES,
    NON_VEGAN_NAMES,
    NON_VEGETARIAN_NAMES,
)

logger = logging.getLogger("kitchenpilot.constraints.dietary")

# Canonical and common root vegetables prohibited under strict Jain rules
JAIN_PROHIBITED_INGREDIENTS: Set[str] = {
    "onion",
    "garlic",
    "potato",
    "carrot",
    "radish",
    "beetroot",
    "ginger",
    "turmeric fresh",
    "sweet potato",
    "yam",
    "taro",
    "colocasia",
    "turnip",
    "shallot",
    "scallion",
    "spring onion",
    "leek",
    "chives",
}

# Ingredients strictly prohibited under Satvik rules
SATVIK_PROHIBITED_INGREDIENTS: Set[str] = {
    "onion",
    "garlic",
    "shallot",
    "scallion",
    "spring onion",
    "leek",
    "mushroom",
    "alcohol",
    "wine",
    "beer",
}

RECIPES_PATH = Path("data/processed/recipes.csv")


class DietaryRuleEngine:
    """Evaluates dietary compliance (Vegetarian, Vegan, Jain, Satvik) and allergen exclusions."""

    def __init__(
        self,
        ingredient_matcher: Optional[IngredientConstraintMatcher] = None,
        recipes_path: Path = RECIPES_PATH,
    ) -> None:
        self.matcher = ingredient_matcher or IngredientConstraintMatcher()
        self.recipes_path = recipes_path
        self._recipes_metadata: Dict[str, Dict[str, Any]] = {}
        self._load_recipes_metadata()

    def _load_recipes_metadata(self) -> None:
        """Load and cache dietary flags and categorical labels from recipes CSV."""
        if not self.recipes_path.is_file():
            logger.warning("Recipes file not found: %s", self.recipes_path)
            return

        df = pd.read_csv(self.recipes_path, low_memory=False)
        for _, row in df.iterrows():
            rid = str(row["recipe_id"]).strip()
            self._recipes_metadata[rid] = {
                "recipe_name": str(row.get("recipe_name", "")).strip(),
                "diet_type": str(row.get("diet_type", "")).strip().lower(),
                "vegetarian": bool(row.get("vegetarian")) if pd.notna(row.get("vegetarian")) else None,
                "vegan": bool(row.get("vegan")) if pd.notna(row.get("vegan")) else None,
                "jain": bool(row.get("jain")) if pd.notna(row.get("jain")) else None,
                "satvik": bool(row.get("satvik")) if pd.notna(row.get("satvik")) else None,
            }

    def detect_constraint_conflicts(
        self,
        dietary: DietaryConstraints,
        required_ingredients: Sequence[str],
        excluded_allergens: Sequence[str],
    ) -> List[str]:
        """Detect logically contradictory constraint requests."""
        conflicts: List[str] = []

        for req in required_ingredients:
            req_clean = req.strip().lower()
            if not req_clean:
                continue

            # Check if required ingredient is non-vegetarian when vegetarian is requested
            if dietary.vegetarian is True:
                if any(nv in req_clean for nv in NON_VEGETARIAN_NAMES):
                    conflicts.append(
                        f"Conflict: required ingredient '{req}' violates required vegetarian constraint."
                    )

            # Check if required ingredient is non-vegan when vegan is requested
            if dietary.vegan is True:
                if any(nv in req_clean for nv in NON_VEGAN_NAMES) or any(
                    nv in req_clean for nv in NON_VEGETARIAN_NAMES
                ):
                    conflicts.append(
                        f"Conflict: required ingredient '{req}' violates required vegan constraint."
                    )

            # Check if required ingredient is root vegetable when Jain is requested
            if dietary.jain is True:
                if any(j in req_clean for j in JAIN_PROHIBITED_INGREDIENTS):
                    conflicts.append(
                        f"Conflict: required ingredient '{req}' is a prohibited root vegetable under Jain rules."
                    )

            # Check if required ingredient is an excluded allergen
            for allergen in excluded_allergens:
                all_clean = allergen.strip().lower()
                if all_clean == "dairy" and any(d in req_clean for d in ["milk", "paneer", "ghee", "butter", "curd", "cheese", "cream", "yogurt"]):
                    conflicts.append(f"Conflict: required ingredient '{req}' contains excluded allergen 'dairy'.")
                elif all_clean in req_clean:
                    conflicts.append(f"Conflict: required ingredient '{req}' matches excluded allergen '{allergen}'.")

        return conflicts

    def evaluate_dietary_compliance(
        self,
        recipe_id: str,
        constraints: DietaryConstraints,
    ) -> Tuple[bool, List[str], Dict[str, ComplianceStatus]]:
        """Evaluate Vegetarian, Vegan, Jain, and Satvik compliance using 3-state semantics."""
        meta = self._recipes_metadata.get(recipe_id)
        hard_failures: List[str] = []
        statuses: Dict[str, ComplianceStatus] = {}

        if not meta:
            return False, ["Recipe metadata not found"], {
                "vegetarian": ComplianceStatus.UNKNOWN,
                "vegan": ComplianceStatus.UNKNOWN,
                "jain": ComplianceStatus.UNKNOWN,
                "satvik": ComplianceStatus.UNKNOWN,
            }

        diet_lower = meta["diet_type"]
        rname_lower = meta["recipe_name"].lower()

        # 1. Vegetarian Evaluation
        if constraints.vegetarian is True:
            # Check explicit metadata flag
            if meta["vegetarian"] is True:
                statuses["vegetarian"] = ComplianceStatus.COMPLIANT
            elif meta["vegetarian"] is False:
                statuses["vegetarian"] = ComplianceStatus.NON_COMPLIANT
                hard_failures.append("Violates vegetarian constraint: marked non-vegetarian.")
            else:
                # Inspect ingredients for non-veg keywords
                clean_ings = self.matcher._recipe_clean_ingredients.get(recipe_id, [])
                if any(any(nv in ing for nv in NON_VEGETARIAN_NAMES) for ing in clean_ings):
                    statuses["vegetarian"] = ComplianceStatus.NON_COMPLIANT
                    hard_failures.append("Violates vegetarian constraint: contains non-vegetarian ingredients.")
                else:
                    statuses["vegetarian"] = ComplianceStatus.COMPLIANT

        # 2. Vegan Evaluation
        if constraints.vegan is True:
            if meta["vegan"] is True or "vegan" in diet_lower or "vegan" in rname_lower:
                statuses["vegan"] = ComplianceStatus.COMPLIANT
            else:
                # Check for animal-derived ingredients or dairy
                clean_ings = self.matcher._recipe_clean_ingredients.get(recipe_id, [])
                has_non_vegan = False
                for ing in clean_ings:
                    if any(nv in ing for nv in NON_VEGAN_NAMES) or any(nv in ing for nv in NON_VEGETARIAN_NAMES):
                        has_non_vegan = True
                        break

                if has_non_vegan or (meta["vegetarian"] is False):
                    statuses["vegan"] = ComplianceStatus.NON_COMPLIANT
                    hard_failures.append("Violates vegan constraint: contains animal-derived or dairy ingredients.")
                elif meta["vegetarian"] is True:
                    # In absence of non-vegan ingredients, check if completely free of dairy
                    statuses["vegan"] = ComplianceStatus.COMPLIANT
                else:
                    statuses["vegan"] = ComplianceStatus.UNKNOWN
                    hard_failures.append("Cannot verify vegan compliance: insufficient ingredient data.")

        # 3. Jain Evaluation
        if constraints.jain is True:
            # Must first satisfy vegetarian
            if meta["vegetarian"] is False:
                statuses["jain"] = ComplianceStatus.NON_COMPLIANT
                hard_failures.append("Violates Jain constraint: recipe is non-vegetarian.")
            elif meta["jain"] is True or "jain" in diet_lower:
                statuses["jain"] = ComplianceStatus.COMPLIANT
            else:
                # Strictly check all recipe ingredients against root vegetables
                clean_ings = self.matcher._recipe_clean_ingredients.get(recipe_id, [])
                found_roots = []
                for ing in clean_ings:
                    for root in JAIN_PROHIBITED_INGREDIENTS:
                        if root in ing:
                            found_roots.append(root)
                            break

                if found_roots:
                    statuses["jain"] = ComplianceStatus.NON_COMPLIANT
                    hard_failures.append(
                        f"Violates Jain constraint: contains prohibited root vegetables ({', '.join(set(found_roots))})."
                    )
                else:
                    statuses["jain"] = ComplianceStatus.COMPLIANT

        # 4. Satvik Evaluation
        if constraints.satvik is True:
            if meta["vegetarian"] is False:
                statuses["satvik"] = ComplianceStatus.NON_COMPLIANT
                hard_failures.append("Violates Satvik constraint: recipe is non-vegetarian.")
            elif meta["satvik"] is True or "satvik" in diet_lower or "sattvic" in diet_lower:
                statuses["satvik"] = ComplianceStatus.COMPLIANT
            else:
                # Check for onion, garlic, mushrooms, alcohol
                clean_ings = self.matcher._recipe_clean_ingredients.get(recipe_id, [])
                found_tamasic = []
                for ing in clean_ings:
                    for prohibited in SATVIK_PROHIBITED_INGREDIENTS:
                        if prohibited in ing:
                            found_tamasic.append(prohibited)
                            break

                if found_tamasic:
                    statuses["satvik"] = ComplianceStatus.NON_COMPLIANT
                    hard_failures.append(
                        f"Violates Satvik constraint: contains prohibited ingredients ({', '.join(set(found_tamasic))})."
                    )
                else:
                    statuses["satvik"] = ComplianceStatus.COMPLIANT

        passed = len(hard_failures) == 0
        return passed, hard_failures, statuses

    def evaluate_allergen_exclusions(
        self,
        recipe_id: str,
        allergens: AllergenConstraints,
    ) -> Tuple[bool, List[str], List[str]]:
        """Evaluate hard allergen exclusions.

        Returns:
            (passed, hard_failures, detected_allergens)
        """
        hard_failures: List[str] = []
        detected_allergens: List[str] = []

        if not allergens.excluded_allergens:
            return True, [], []

        clean_allergens = [a.strip().lower() for a in allergens.excluded_allergens if a.strip()]
        if not clean_allergens:
            return True, [], []

        # Get recipe ingredients
        clean_ings = self.matcher._recipe_clean_ingredients.get(recipe_id, [])
        canon_cids = self.matcher._recipe_canonical_ids.get(recipe_id, set())

        # Check canonical ingredient flags from ontology
        recipe_allergen_flags: Set[str] = set()
        for cid in canon_cids:
            ing_obj = self.matcher.ontology.get_by_id(cid)
            if ing_obj and ing_obj.allergen_flags:
                recipe_allergen_flags.update(f.lower() for f in ing_obj.allergen_flags)

        # Map text keywords for common allergen groups
        for exc in clean_allergens:
            is_present = False
            # Check ontology flags
            if exc in recipe_allergen_flags:
                is_present = True

            # Direct lexical matching for dairy variants
            if exc == "dairy":
                dairy_keywords = ["milk", "curd", "yogurt", "paneer", "ghee", "butter", "cheese", "cream"]
                if any(any(dk in ing for dk in dairy_keywords) for ing in clean_ings):
                    is_present = True

            # Direct matching for nuts
            elif exc in ("peanut", "peanuts"):
                if any("peanut" in ing for ing in clean_ings):
                    is_present = True
            elif exc in ("tree_nut", "tree_nuts", "nuts"):
                nut_keywords = ["cashew", "almond", "walnut", "pistachio", "pista", "badam", "kaju"]
                if any(any(nk in ing for nk in nut_keywords) for ing in clean_ings):
                    is_present = True

            # Direct matching for gluten
            elif exc == "gluten":
                gluten_keywords = ["wheat", "maida", "sooji", "semolina", "rava", "atta"]
                if any(any(gk in ing for gk in gluten_keywords) for ing in clean_ings):
                    is_present = True

            # Direct keyword check
            elif any(exc in ing for ing in clean_ings):
                is_present = True

            if is_present:
                detected_allergens.append(exc)
                hard_failures.append(f"Contains excluded allergen: '{exc}' (HARD REJECT).")

        passed = len(hard_failures) == 0
        return passed, hard_failures, detected_allergens
