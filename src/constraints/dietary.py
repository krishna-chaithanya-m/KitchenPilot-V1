"""Dietary and Allergen Rule Engine for KitchenPilot-V1.

Implements 3-state compliance (COMPLIANT, NON_COMPLIANT, UNKNOWN) for
Vegetarian, Vegan, Jain, and Satvik rules, hard allergen exclusions,
and impossible constraint conflict detection.
"""

from __future__ import annotations

import logging
import re
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
    NON_VEGAN_CATEGORIES,
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

PROHIBITED_NON_VEG_PATTERNS = [
    # Meats & poultry
    r"\bchicken\b", r"\bmutton\b", r"\blamb\b", r"\bpork\b", r"\bbeef\b",
    r"\bveal\b", r"\bduck\b", r"\bturkey\b(?!(\s+berry|\s+chutney))", r"\bpoultry\b", r"\bkeema\b",
    r"\bkheema\b", r"\bgosht\b", r"\bmurgh\b", r"\bmurg\b", r"\bbacon\b",
    # Fish & seafood
    r"\bfish\b", r"\bfishes\b", r"\bprawn\b", r"\bprawns\b", r"\bshrimp\b",
    r"\bshrimps\b", r"\bcrab\b", r"\bcrabs\b", r"\blobster\b", r"\blobsters\b",
    r"\bseafood\b", r"\bsquid\b", r"\bsquids\b", r"\bcalamari\b", r"\bclam\b",
    r"\bclams\b", r"\boyster\b", r"\boysters\b", r"\banchov(?:y|ies)\b",
    r"\bpomfret\b", r"\bsalmon\b", r"\btuna\b", r"\bsardine\b", r"\bsardines\b",
    r"\bhilsa\b", r"\brohu\b", r"\bkatla\b", r"\bsurmai\b", r"\bmaach\b",
    r"\bmachh\b", r"\bmachli\b", r"\bbhetki\b",
    # Hindi / Devanagari non-veg terms
    r"अंडे", r"अंडा", r"मछली", r"चिकन", r"मटन", r"गोश्त",
]

_RE_NON_VEG = re.compile("|".join(PROHIBITED_NON_VEG_PATTERNS), re.IGNORECASE)
_RE_EGG = re.compile(r"\b(?:eggs?|baida)\b", re.IGNORECASE)
_RE_MEAT = re.compile(r"\bmeat\b", re.IGNORECASE)
_RE_HAM = re.compile(r"\bham\b", re.IGNORECASE)


def clean_negations_and_context(text: str) -> str:
    """Strip negated phrases, mock terms, spice mix contexts, and serving suggestions.

    Prevents false-positive dietary violations from titles and ingredient descriptions
    such as 'No Onion No Garlic Paneer', 'Jain Pav Bhaji (No Potato)', 'Mock Chicken',
    'Soya Keema', 'Meat Masala Powder', 'Eggless Omelette', etc.
    """
    if not text:
        return ""
    t = text.lower().strip()

    # 1. Negated onion, garlic, roots, tamasic
    t = re.sub(
        r"\b(?:no|without|zero|free\s*from)\s+(?:onion\s*(?:and|&|or|,)?\s*|garlic\s*(?:and|&|or|,)?\s*)+",
        " ",
        t,
    )
    t = re.sub(
        r"\b(?:onion|garlic|potato|root)\s*-\s*free\b|\b(?:onion|garlic|potato|root)\s+free\b",
        " ",
        t,
    )
    t = re.sub(
        r"\b(?:no|without)\s+(?:potato|potatoes|carrot|carrots|beetroot|beetroots|radish|radishes|ginger|mushrooms?)\b",
        " ",
        t,
    )

    # 2. Negated eggs and egg-free
    t = re.sub(
        r"\b(?:no|without)\s+(?:eggs?|baida)\b|\b(?:egg|baida)[-\s]free\b|\beggless\b",
        " ",
        t,
    )

    # 3. Mock and plant-based meats
    t = re.sub(
        r"\b(?:mock|plant[-\s]based|vegan|vegetarian|veg|soya|soy)\s+(?:scrambled\s+)?(?:chicken|meat|fish|mutton|prawn|prawns|beef|pork|duck|keema|kheema|eggs?|omelette|bacon)\b",
        " ",
        t,
    )
    t = re.sub(
        r"\b(?:paneer|mushroom|matar|mutter|cabbage|broccoli)\s+(?:keema|kheema)\b",
        " ",
        t,
    )

    # 4. Spice blends / masala powders (e.g. 'meat masala', 'fish curry masala powder', 'chicken masala')
    t = re.sub(
        r"\b(?:meat|chicken|fish|mutton)\s+(?:masala|curry\s+masala|fry\s+masala|spice)(?:\s+(?:powder|mix|blend))?\b",
        " ",
        t,
    )

    # 5. Serving suggestions (e.g. 'for chicken biryani', 'serve with fish')
    t = re.sub(
        r"\b(?:serve\s+with|side\s+dish\s+for|accompaniment\s+for|for)\s+(?:chicken|fish|mutton|meat|beef|prawns?)\b",
        " ",
        t,
    )

    # 6. Specific translation artifacts in recipe titles
    t = re.sub(r"\bcoffee\s+and\s+beef\b", " ", t)
    t = re.sub(r"\bchickens\s+togayal\b", "togayal", t)
    t = re.sub(r"\bturkey\s+chutney\b", "chutney", t)

    return t


def detect_prohibited_non_veg(text: str) -> Optional[str]:
    """Detect non-vegetarian terms in arbitrary ingredient or recipe text.

    Distinguishes legitimate vegetarian uses such as eggplant, eggless,
    flaxmeal egg replacer, tender coconut meat, and meat masala.
    """
    if not text:
        return None
    raw_lower = text.lower().strip()
    if any(ep in raw_lower for ep in ["eggplant", "egg plant", "egg-plant", "eggplants", "egg-plants"]):
        raw_without_ep = re.sub(r"\begg[-\s]?plants?\b", " ", raw_lower)
        if not any(nv in raw_without_ep for nv in ["chicken", "mutton", "fish", "meat", "prawn", "beef", "pork"]):
            return None

    t = clean_negations_and_context(text)
    m = _RE_NON_VEG.search(t)
    if m:
        return m.group(0)
    if _RE_EGG.search(t):
        if not any(ex in t for ex in ["eggplant", "egg plant", "egg-plant", "eggless", "egg replacer", "egg-free", "egg free"]):
            return "egg"
    if _RE_MEAT.search(t):
        if not any(ex in t for ex in ["coconut meat", "meat masala", "sweetmeat", "soya meat", "soy meat", "mock meat"]):
            return "meat"
    if _RE_HAM.search(t):
        if not any(ex in t for ex in ["graham", "chamomile", "khaman"]):
            return "ham"
    return None


def detect_prohibited_non_vegan(text: str) -> Optional[str]:
    """Detect animal-derived or dairy ingredients in text."""
    if not text:
        return None
    t = clean_negations_and_context(text)
    # First check non-veg
    nv = detect_prohibited_non_veg(t)
    if nv:
        return nv

    # Dairy / honey
    for nv_name in NON_VEGAN_NAMES:
        if re.search(r"\b" + re.escape(nv_name) + r"\b", t):
            # Safe plant-based exceptions
            if nv_name == "milk" and any(pm in t for pm in ["coconut milk", "almond milk", "soy milk", "soya milk", "oat milk", "cashew milk"]):
                continue
            if nv_name == "butter" and any(pb in t for pb in ["peanut butter", "cocoa butter", "apple butter", "shea butter"]):
                continue
            if nv_name == "cream" and any(pc in t for pc in ["coconut cream", "almond cream", "soy cream"]):
                continue
            return nv_name
    return None


def detect_satvik_prohibited(text: str) -> Optional[str]:
    """Detect onion, garlic, mushrooms, alcohol, and other tamasic ingredients."""
    if not text:
        return None
    t = clean_negations_and_context(text)
    for prohibited in SATVIK_PROHIBITED_INGREDIENTS:
        if re.search(r"\b" + re.escape(prohibited) + r"\b", t):
            return prohibited
    return None


def detect_jain_prohibited(text: str) -> Optional[str]:
    """Detect prohibited root vegetables under strict Jain rules."""
    if not text:
        return None
    t = clean_negations_and_context(text)
    for root in JAIN_PROHIBITED_INGREDIENTS:
        if re.search(r"\b" + re.escape(root) + r"\b", t):
            return root
    return None


def is_dairy_ingredient(text: str) -> bool:
    """Check if an ingredient text represents dairy, ignoring plant-based milks and butters."""
    if not text:
        return False
    t = text.lower().strip()
    dairy_keywords = ["milk", "curd", "yogurt", "paneer", "ghee", "butter", "cheese", "cream"]
    for dk in dairy_keywords:
        if re.search(r"\b" + re.escape(dk) + r"\b", t):
            if dk == "milk" and any(pm in t for pm in ["coconut milk", "almond milk", "soy milk", "soya milk", "oat milk", "cashew milk"]):
                continue
            if dk == "butter" and any(pb in t for pb in ["peanut butter", "cocoa butter", "apple butter", "shea butter"]):
                continue
            if dk == "cream" and any(pc in t for pc in ["coconut cream", "almond cream", "soy cream"]):
                continue
            return True
    return False


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
                "ingredients_text": str(row.get("ingredients", "")).strip().lower() if pd.notna(row.get("ingredients")) else "",
            }

    def _get_recipe_ingredient_texts(self, recipe_id: str) -> List[str]:
        """Collect all available ingredient textual representations for a recipe."""
        texts: List[str] = []
        clean_ings = self.matcher._recipe_clean_ingredients.get(recipe_id, [])
        texts.extend(clean_ings)

        raw_ings = self.matcher._recipe_raw_ingredients.get(recipe_id, [])
        texts.extend(raw_ings)

        canon_names = self.matcher._recipe_canonical_names.get(recipe_id, set())
        texts.extend(canon_names)

        meta = self._recipes_metadata.get(recipe_id, {})
        raw_meta = meta.get("ingredients_text", "")
        if raw_meta:
            texts.extend([i.strip() for i in raw_meta.split(",") if i.strip()])

        return texts

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
                nv = detect_prohibited_non_veg(req_clean)
                if nv:
                    conflicts.append(
                        f"Conflict: required ingredient '{req}' violates required vegetarian constraint."
                    )

            # Check if required ingredient is prohibited under Satvik rules
            if dietary.satvik is True:
                nv = detect_prohibited_non_veg(req_clean)
                if nv:
                    conflicts.append(
                        f"Conflict: required ingredient '{req}' violates required Satvik constraint (non-vegetarian)."
                    )
                satvik_tam = detect_satvik_prohibited(req_clean)
                if satvik_tam:
                    conflicts.append(
                        f"Conflict: required ingredient '{req}' is a prohibited ingredient under Satvik rules."
                    )

            # Check if required ingredient is non-vegan when vegan is requested
            if dietary.vegan is True:
                nvg = detect_prohibited_non_vegan(req_clean)
                if nvg:
                    conflicts.append(
                        f"Conflict: required ingredient '{req}' violates required vegan constraint."
                    )

            # Check if required ingredient is root vegetable when Jain is requested
            if dietary.jain is True:
                nv = detect_prohibited_non_veg(req_clean)
                if nv:
                    conflicts.append(
                        f"Conflict: required ingredient '{req}' violates required Jain constraint (non-vegetarian)."
                    )
                elif detect_jain_prohibited(req_clean):
                    conflicts.append(
                        f"Conflict: required ingredient '{req}' is a prohibited root vegetable under Jain rules."
                    )

            # Check if required ingredient is an excluded allergen
            for allergen in excluded_allergens:
                all_clean = allergen.strip().lower()
                if all_clean == "dairy" and is_dairy_ingredient(req_clean):
                    conflicts.append(f"Conflict: required ingredient '{req}' contains excluded allergen 'dairy'.")
                elif all_clean != "dairy" and all_clean in req_clean:
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
        ing_texts = self._get_recipe_ingredient_texts(recipe_id)
        has_ingredients = len(ing_texts) > 0

        # Step 0: Check for non-vegetarian evidence across all sources
        non_veg_detected: Optional[str] = None

        # Check explicit non-veg diet label
        if any(term in diet_lower for term in ["non vegetarian", "non vegeterian", "non-vegetarian", "non-vegeterian", "non veg", "non-veg", "eggetarian"]):
            non_veg_detected = meta["diet_type"]

        # Check explicit metadata flag (unless diet_type indicates sattvic or vegan where vegetarian flag was historically omitted)
        elif meta["vegetarian"] is False and not (
            "sattvic" in diet_lower or "satvik" in diet_lower or "no onion no garlic" in diet_lower or "vegan" in diet_lower
        ):
            non_veg_detected = "marked non-vegetarian"

        # Check recipe title
        if not non_veg_detected:
            title_match = detect_prohibited_non_veg(rname_lower)
            if title_match:
                non_veg_detected = f"title contains '{title_match}'"

        # Check all ingredient texts
        if not non_veg_detected:
            for ing in ing_texts:
                ing_match = detect_prohibited_non_veg(ing)
                if ing_match:
                    non_veg_detected = f"ingredient contains '{ing_match}'"
                    break

        # Check canonical ontology categories
        if not non_veg_detected:
            canon_cids = self.matcher._recipe_canonical_ids.get(recipe_id, set())
            for cid in canon_cids:
                ing_obj = self.matcher.ontology.get_by_id(cid)
                if ing_obj and (ing_obj.category in {"meat", "egg"} or not ing_obj.vegetarian):
                    non_veg_detected = f"canonical ingredient '{ing_obj.canonical_name}' is non-vegetarian"
                    break

        is_definitely_non_veg = non_veg_detected is not None

        # 1. Vegetarian Evaluation
        if constraints.vegetarian is True:
            if is_definitely_non_veg:
                statuses["vegetarian"] = ComplianceStatus.NON_COMPLIANT
                hard_failures.append(f"Violates vegetarian constraint: {non_veg_detected}.")
            elif not has_ingredients:
                statuses["vegetarian"] = ComplianceStatus.UNKNOWN
                hard_failures.append("Cannot verify vegetarian compliance: insufficient ingredient data.")
            else:
                statuses["vegetarian"] = ComplianceStatus.COMPLIANT

        # 2. Vegan Evaluation
        if constraints.vegan is True:
            if is_definitely_non_veg:
                statuses["vegan"] = ComplianceStatus.NON_COMPLIANT
                hard_failures.append(f"Violates vegan constraint: {non_veg_detected}.")
            elif not has_ingredients:
                statuses["vegan"] = ComplianceStatus.UNKNOWN
                hard_failures.append("Cannot verify vegan compliance: insufficient ingredient data.")
            else:
                found_non_vegan: List[str] = []
                for ing in ing_texts:
                    nvg = detect_prohibited_non_vegan(ing)
                    if nvg:
                        found_non_vegan.append(nvg)

                canon_cids = self.matcher._recipe_canonical_ids.get(recipe_id, set())
                for cid in canon_cids:
                    ing_obj = self.matcher.ontology.get_by_id(cid)
                    if ing_obj and (ing_obj.category in NON_VEGAN_CATEGORIES or not ing_obj.vegan):
                        found_non_vegan.append(ing_obj.canonical_name)

                if found_non_vegan:
                    statuses["vegan"] = ComplianceStatus.NON_COMPLIANT
                    hard_failures.append(
                        f"Violates vegan constraint: contains animal-derived or dairy ingredients ({', '.join(sorted(set(found_non_vegan)))})."
                    )
                else:
                    statuses["vegan"] = ComplianceStatus.COMPLIANT

        # 3. Jain Evaluation
        if constraints.jain is True:
            if is_definitely_non_veg:
                statuses["jain"] = ComplianceStatus.NON_COMPLIANT
                hard_failures.append(f"Violates Jain constraint: {non_veg_detected}.")
            elif not has_ingredients:
                statuses["jain"] = ComplianceStatus.UNKNOWN
                hard_failures.append("Cannot verify Jain compliance: insufficient ingredient data.")
            else:
                found_roots: List[str] = []
                for ing in ing_texts:
                    root = detect_jain_prohibited(ing)
                    if root:
                        found_roots.append(root)
                title_root = detect_jain_prohibited(rname_lower)
                if title_root:
                    found_roots.append(title_root)

                if found_roots:
                    statuses["jain"] = ComplianceStatus.NON_COMPLIANT
                    hard_failures.append(
                        f"Violates Jain constraint: contains prohibited root vegetables ({', '.join(sorted(set(found_roots)))})."
                    )
                else:
                    statuses["jain"] = ComplianceStatus.COMPLIANT

        # 4. Satvik Evaluation
        if constraints.satvik is True:
            if is_definitely_non_veg:
                statuses["satvik"] = ComplianceStatus.NON_COMPLIANT
                hard_failures.append(f"Violates Satvik constraint: {non_veg_detected}.")
            elif not has_ingredients:
                statuses["satvik"] = ComplianceStatus.UNKNOWN
                hard_failures.append("Cannot verify Satvik compliance: insufficient ingredient data.")
            else:
                found_tamasic: List[str] = []
                for ing in ing_texts:
                    tam = detect_satvik_prohibited(ing)
                    if tam:
                        found_tamasic.append(tam)
                title_tam = detect_satvik_prohibited(rname_lower)
                if title_tam:
                    found_tamasic.append(title_tam)

                if found_tamasic:
                    statuses["satvik"] = ComplianceStatus.NON_COMPLIANT
                    hard_failures.append(
                        f"Violates Satvik constraint: contains prohibited ingredients ({', '.join(sorted(set(found_tamasic)))})."
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

        # Get recipe ingredients across all textual representations
        clean_ings = self._get_recipe_ingredient_texts(recipe_id)
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
                if any(is_dairy_ingredient(ing) for ing in clean_ings):
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
