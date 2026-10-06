"""Authoritative Recipe Corpus and Text Representation for Semantic Retrieval.

Builds deterministic, information-dense recipe representations including recipe name,
cuisine, region, meal course, category, dietary attributes, and clean ingredient names.
Avoids database primary keys, internal hashes, timestamps, or raw numeric IDs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger("kitchenpilot.retrieval.corpus")


def build_recipe_semantic_text(
    recipe_name: str,
    cuisine: Optional[str] = None,
    region: Optional[str] = None,
    meal_type: Optional[str] = None,
    category: Optional[str] = None,
    diet_type: Optional[str] = None,
    vegetarian: Optional[bool] = None,
    vegan: Optional[bool] = None,
    jain: Optional[bool] = None,
    satvik: Optional[bool] = None,
    ingredients: Optional[Sequence[str]] = None,
) -> str:
    """Build a deterministic, semantic text representation of a recipe for dense retrieval.

    Follows Stage D requirements:
    - Includes: recipe name, cuisine, region, meal course, category, dietary attributes, ingredients.
    - Excludes: internal IDs, source hashes, timestamps, database metadata, arbitrary numbers.
    """
    clean_name = str(recipe_name).strip() if recipe_name else ""
    parts: List[str] = [clean_name]

    if cuisine and str(cuisine).strip() and str(cuisine).strip().lower() != "nan":
        parts.append(f"Cuisine: {str(cuisine).strip()}")

    if region and str(region).strip() and str(region).strip().lower() != "nan":
        parts.append(f"Region: {str(region).strip()}")

    if meal_type and str(meal_type).strip() and str(meal_type).strip().lower() != "nan":
        parts.append(f"Meal Type: {str(meal_type).strip()}")

    if category and str(category).strip() and str(category).strip().lower() != "nan":
        cat_str = str(category).strip()
        meal_str = str(meal_type).strip() if meal_type else ""
        if not meal_str or cat_str.lower() != meal_str.lower():
            parts.append(f"Category: {cat_str}")

    diet_tokens: List[str] = []
    if diet_type and str(diet_type).strip() and str(diet_type).strip().lower() != "nan":
        diet_tokens.append(str(diet_type).strip())

    existing_lower = {d.lower() for d in diet_tokens}
    if vegetarian and "vegetarian" not in existing_lower:
        diet_tokens.append("Vegetarian")
    if vegan and "vegan" not in existing_lower:
        diet_tokens.append("Vegan")
    if jain and "jain" not in existing_lower:
        diet_tokens.append("Jain")
    if satvik and "satvik" not in existing_lower:
        diet_tokens.append("Satvik")

    if diet_tokens:
        parts.append(f"Diet: {', '.join(diet_tokens)}")

    if ingredients:
        clean_ings = [
            str(ing).strip()
            for ing in ingredients
            if ing is not None and str(ing).strip() and str(ing).strip().lower() != "nan"
        ]
        if clean_ings:
            parts.append(f"Ingredients: {', '.join(clean_ings)}")

    return ". ".join(parts)


def build_query_semantic_text(
    query: Optional[str] = None,
    available_ingredients: Optional[Sequence[str]] = None,
    cuisine: Optional[str] = None,
    region: Optional[str] = None,
    meal_type: Optional[str] = None,
    diet_type: Optional[str] = None,
    vegetarian: Optional[bool] = None,
    vegan: Optional[bool] = None,
    jain: Optional[bool] = None,
    satvik: Optional[bool] = None,
) -> str:
    """Build a deterministic query string for semantic retrieval.

    If a free-form natural language query is provided, it serves as the base.
    Additional structured preferences or ingredient lists are deterministically appended.
    """
    parts: List[str] = []

    if query and query.strip():
        parts.append(query.strip())

    if cuisine and str(cuisine).strip():
        parts.append(f"Cuisine: {str(cuisine).strip()}")

    if region and str(region).strip():
        parts.append(f"Region: {str(region).strip()}")

    if meal_type and str(meal_type).strip():
        parts.append(f"Meal Type: {str(meal_type).strip()}")

    diet_tokens: List[str] = []
    if diet_type and str(diet_type).strip():
        diet_tokens.append(str(diet_type).strip())
    existing_lower = {d.lower() for d in diet_tokens}
    if vegetarian and "vegetarian" not in existing_lower:
        diet_tokens.append("Vegetarian")
    if vegan and "vegan" not in existing_lower:
        diet_tokens.append("Vegan")
    if jain and "jain" not in existing_lower:
        diet_tokens.append("Jain")
    if satvik and "satvik" not in existing_lower:
        diet_tokens.append("Satvik")
    if diet_tokens:
        parts.append(f"Diet: {', '.join(diet_tokens)}")

    if available_ingredients:
        clean_ings = [
            str(i).strip()
            for i in available_ingredients
            if str(i).strip() and str(i).strip().lower() != "nan"
        ]
        if clean_ings:
            parts.append(f"Ingredients: {', '.join(clean_ings)}")

    return ". ".join(parts) if parts else ""


class RecipeCorpus:
    """Manages loading and deterministic text representation of the recipe corpus."""

    def __init__(
        self,
        recipes_path: Path,
        linked_ingredients_path: Optional[Path] = None,
    ) -> None:
        self.recipes_path = recipes_path
        self.linked_ingredients_path = linked_ingredients_path
        self.recipe_ids: List[str] = []
        self.recipe_texts: List[str] = []
        self.recipe_to_row: Dict[str, int] = {}
        self.row_to_recipe: Dict[int, str] = {}
        self._load_and_build()

    def _load_and_build(self) -> None:
        """Load datasets and build deterministic text representations."""
        if not self.recipes_path.is_file():
            raise FileNotFoundError(f"Recipes file not found: {self.recipes_path}")

        df = pd.read_csv(self.recipes_path)
        # Enforce strict deterministic sorting by recipe_id ascending
        df = df.sort_values(by="recipe_id", ascending=True).reset_index(drop=True)

        # Pre-index linked ingredients if available
        ing_map: Dict[str, List[str]] = {}
        if self.linked_ingredients_path and self.linked_ingredients_path.is_file():
            try:
                ing_df = pd.read_csv(self.linked_ingredients_path)
                # Group ingredients in original order for each recipe
                for _, row in ing_df.iterrows():
                    rid = str(row["recipe_id"]).strip()
                    ing_name = row.get("ingredient")
                    if pd.notna(ing_name) and str(ing_name).strip():
                        ing_map.setdefault(rid, []).append(str(ing_name).strip())
            except Exception as e:
                logger.warning("Failed to load linked ingredients: %s", e)

        self.recipe_ids = []
        self.recipe_texts = []
        self.recipe_to_row = {}
        self.row_to_recipe = {}

        for idx, row in df.iterrows():
            rid = str(row["recipe_id"]).strip()
            name = str(row.get("recipe_name", "")).strip()
            cuisine = row.get("cuisine")
            region = row.get("region")
            meal_type = row.get("meal_type")
            category = row.get("category")
            diet_type = row.get("diet_type")
            vegetarian = bool(row.get("vegetarian")) if pd.notna(row.get("vegetarian")) else None
            vegan = bool(row.get("vegan")) if pd.notna(row.get("vegan")) else None
            jain = bool(row.get("jain")) if pd.notna(row.get("jain")) else None
            satvik = bool(row.get("satvik")) if pd.notna(row.get("satvik")) else None

            # Ingredients from linked mapping, fallback to raw string split if missing
            ings = ing_map.get(rid)
            if not ings and pd.notna(row.get("ingredients")):
                raw_ing_str = str(row.get("ingredients", ""))
                ings = [i.strip() for i in raw_ing_str.split(",") if i.strip()]

            text = build_recipe_semantic_text(
                recipe_name=name,
                cuisine=cuisine if pd.notna(cuisine) else None,
                region=region if pd.notna(region) else None,
                meal_type=meal_type if pd.notna(meal_type) else None,
                category=category if pd.notna(category) else None,
                diet_type=diet_type if pd.notna(diet_type) else None,
                vegetarian=vegetarian,
                vegan=vegan,
                jain=jain,
                satvik=satvik,
                ingredients=ings,
            )

            self.recipe_ids.append(rid)
            self.recipe_texts.append(text)
            self.recipe_to_row[rid] = idx
            self.row_to_recipe[idx] = rid

    def __len__(self) -> int:
        return len(self.recipe_ids)
