"""Corpus Builder for KitchenPilot-V1 Recommendation Engine.

Builds a deterministic recipe text corpus combining recipe metadata and canonical ingredients,
heavily prioritizing ingredients while excluding cooking instructions.
"""

from __future__ import annotations

import re
import string
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.recommendation.config import RecommendationConfig


def normalize_corpus_text(text: str) -> str:
    """Normalize corpus text: lowercase, remove punctuation, collapse whitespace."""
    if not text:
        return ""
    # Lowercase
    text = str(text).lower()
    # Replace punctuation with spaces to avoid concatenating words
    for punct in string.punctuation:
        text = text.replace(punct, " ")
    # Replace multiple whitespaces/newlines with single space
    text = re.sub(r"\s+", " ", text).strip()
    return text


class CorpusBuilder:
    """Constructs a deterministic recipe text corpus for TF-IDF indexing."""

    def __init__(self, config: Optional[RecommendationConfig] = None) -> None:
        self.config = config or RecommendationConfig()

    def build_corpus(self) -> pd.DataFrame:
        """Build the complete recipe text corpus dataframe."""
        recipes_df = pd.read_csv(self.config.recipes_path)
        linked_df = pd.read_csv(self.config.linked_ingredients_path)

        # Group canonical and clean ingredients by recipe_id
        recipe_ingredients: Dict[str, List[str]] = {}
        for _, row in linked_df.iterrows():
            rid = str(row["recipe_id"]).strip()
            if rid not in recipe_ingredients:
                recipe_ingredients[rid] = []

            # Prioritize canonical ingredient name if present, else cleaned ingredient
            canon = str(row["canonical_ingredient"]).strip() if pd.notna(row.get("canonical_ingredient")) else ""
            disp = str(row["display_name"]).strip() if pd.notna(row.get("display_name")) else ""
            ing = str(row["ingredient"]).strip() if pd.notna(row.get("ingredient")) else ""

            # Use canonical name if available, else display name, else raw ingredient name
            chosen_name = canon if canon else (disp if disp else ing)
            norm_name = normalize_corpus_text(chosen_name)
            if norm_name:
                recipe_ingredients[rid].append(norm_name)

        corpus_rows: List[Dict[str, str]] = []
        ing_weight = self.config.ingredient_repetition_weight

        for _, rrow in recipes_df.iterrows():
            rid = str(rrow["recipe_id"]).strip()
            rname = str(rrow["recipe_name"]).strip() if pd.notna(rrow.get("recipe_name")) else ""
            cuisine = str(rrow["cuisine"]).strip() if pd.notna(rrow.get("cuisine")) else ""
            region = str(rrow["region"]).strip() if pd.notna(rrow.get("region")) else ""
            meal_type = str(rrow["meal_type"]).strip() if pd.notna(rrow.get("meal_type")) else ""
            category = str(rrow["category"]).strip() if pd.notna(rrow.get("category")) else ""
            diet_type = str(rrow["diet_type"]).strip() if pd.notna(rrow.get("diet_type")) else ""

            # Ingredients for this recipe
            ings = recipe_ingredients.get(rid, [])
            # Deduplicate ingredients while preserving order
            unique_ings = []
            seen_ings = set()
            for i in ings:
                if i not in seen_ings:
                    seen_ings.add(i)
                    unique_ings.append(i)

            # Build prioritized token list
            parts: List[str] = []
            if rname:
                parts.append(normalize_corpus_text(rname))
            if cuisine:
                parts.append(normalize_corpus_text(cuisine))
            if region:
                parts.append(normalize_corpus_text(region))
            if meal_type:
                parts.append(normalize_corpus_text(meal_type))
            if category:
                parts.append(normalize_corpus_text(category))
            if diet_type:
                parts.append(normalize_corpus_text(diet_type))

            # Heavily prioritize ingredients by repeating them
            ing_string = " ".join(unique_ings)
            for _ in range(ing_weight):
                if ing_string:
                    parts.append(ing_string)

            corpus_text = " ".join(parts)
            corpus_rows.append({
                "recipe_id": rid,
                "recipe_name": rname,
                "corpus_text": corpus_text,
            })

        corpus_df = pd.DataFrame(corpus_rows, columns=["recipe_id", "recipe_name", "corpus_text"])
        return corpus_df

    def save_corpus(self, corpus_df: Optional[pd.DataFrame] = None) -> Path:
        """Build and save recipe corpus to disk."""
        if corpus_df is None:
            corpus_df = self.build_corpus()
        self.config.corpus_path.parent.mkdir(parents=True, exist_ok=True)
        corpus_df.to_csv(self.config.corpus_path, index=False)
        return self.config.corpus_path
