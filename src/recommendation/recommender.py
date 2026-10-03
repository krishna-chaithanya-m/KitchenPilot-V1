"""Main Recommender Interface for KitchenPilot-V1.

Integrates TF-IDF similarity, canonical ingredient matching, nutrition scoring,
preference filtering, hybrid ranking, and deterministic explainability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd

from src.recommendation.config import RecommendationConfig
from src.recommendation.explainability import ExplanationGenerator
from src.recommendation.hybrid_ranker import HybridRanker, ScoredCandidate
from src.recommendation.ingredient_matcher import IngredientMatcher
from src.recommendation.nutrition_scorer import NutritionGoals, NutritionScorer
from src.recommendation.preference_filter import PreferenceFilter, UserPreferences
from src.recommendation.tfidf_model import TFIDFModel

RECOMMENDATION_COLUMNS = [
    "rank",
    "recipe_id",
    "recipe_name",
    "hybrid_score",
    "similarity_score",
    "ingredient_match_score",
    "nutrition_score",
    "preference_score",
    "nutrition_confidence",
    "matched_ingredients",
    "missing_ingredients",
    "explanation",
]


class KitchenPilotRecommender:
    """Production Recommendation Engine for KitchenPilot-V1."""

    def __init__(self, config: Optional[RecommendationConfig] = None) -> None:
        self.config = config or RecommendationConfig()
        self.tfidf_model = TFIDFModel(self.config)
        self.ingredient_matcher = IngredientMatcher(self.config)
        self.nutrition_scorer = NutritionScorer(self.config)
        self.preference_filter = PreferenceFilter(self.config)
        self.hybrid_ranker = HybridRanker(self.config)
        self.explanation_generator = ExplanationGenerator()

        self._recipe_names: Dict[str, str] = {}
        self._load_recipe_names()

        # Load TF-IDF artifacts if available
        if self.config.tfidf_matrix_path.is_file():
            self.tfidf_model.load_artifacts()

    def _load_recipe_names(self) -> None:
        """Load mapping from recipe_id to recipe_name."""
        if self.config.recipes_path.is_file():
            df = pd.read_csv(self.config.recipes_path)
            for _, row in df.iterrows():
                rid = str(row["recipe_id"]).strip()
                rname = str(row["recipe_name"]).strip() if pd.notna(row["recipe_name"]) else ""
                self._recipe_names[rid] = rname

    def recommend(
        self,
        query_recipe_id: Optional[str] = None,
        available_ingredients: Optional[List[str]] = None,
        user_preferences: Optional[UserPreferences] = None,
        nutrition_goals: Optional[NutritionGoals] = None,
        top_k: int = 10,
        save_results: bool = True,
    ) -> pd.DataFrame:
        """Generate top_k hybrid recipe recommendations.

        Supports:
        - Mode A: Recipe-based recommendation (query_recipe_id)
        - Mode B: Ingredient-based recommendation (available_ingredients)
        - Combined: Both recipe and ingredients + preferences + nutrition goals
        """
        if self.tfidf_model.tfidf_matrix is None:
            raise RuntimeError("TF-IDF model artifacts not loaded. Please build the model first.")

        all_rids = self.tfidf_model.recipe_ids
        prefs = user_preferences or UserPreferences()
        goals = nutrition_goals or NutritionGoals()

        # 1. Apply hard dietary and exclusion filters BEFORE ranking
        candidates_rids: List[str] = []
        for rid in all_rids:
            # Exclude the input recipe itself in Mode A
            if query_recipe_id and rid == query_recipe_id:
                continue
            if self.preference_filter.passes_hard_filters(rid, prefs, self.ingredient_matcher):
                candidates_rids.append(rid)

        if not candidates_rids:
            # No candidate passed hard filters
            empty_df = pd.DataFrame(columns=RECOMMENDATION_COLUMNS)
            if save_results:
                empty_df.to_csv(self.config.recommendation_results_path, index=False)
            return empty_df

        # 2. Compute similarity scores
        if query_recipe_id:
            query_vec = self.tfidf_model.get_recipe_vector(query_recipe_id)
            sim_scores_all = self.tfidf_model.compute_similarity_scores(query_vec)
        elif available_ingredients:
            # Transform available ingredients into a query vector
            resolved_avail = [self.ingredient_matcher.resolve_ingredient(i) for i in available_ingredients]
            query_text = " ".join([i for i in resolved_avail if i])
            query_vec = self.tfidf_model.transform_text(query_text)
            sim_scores_all = self.tfidf_model.compute_similarity_scores(query_vec)
        else:
            sim_scores_all = np.zeros(len(all_rids), dtype=float)

        # Map candidate scores
        recipe_to_row = self.tfidf_model.recipe_to_row

        # 3. Score all passing candidates across the 4 pillars
        scored_candidates: List[ScoredCandidate] = []
        has_avail = bool(available_ingredients)
        total_avail = len(available_ingredients) if available_ingredients else 0

        for rid in candidates_rids:
            row_idx = recipe_to_row[rid]
            sim_score = float(sim_scores_all[row_idx])

            # Pillar 2: Ingredient match
            ing_res = self.ingredient_matcher.match_recipe(
                recipe_id=rid,
                available_ingredients=available_ingredients,
                required_ingredients=prefs.required_ingredients,
            )

            # Pillar 3: Nutrition score
            nut_res = self.nutrition_scorer.score_recipe(rid, goals)

            # Pillar 4: Preference compatibility
            pref_score, matched_prefs = self.preference_filter.compute_preference_score(rid, prefs)

            rname = self._recipe_names.get(rid, "")

            cand = ScoredCandidate(
                recipe_id=rid,
                recipe_name=rname,
                similarity_score=sim_score,
                ingredient_match_score=ing_res.match_score,
                nutrition_score=nut_res.nutrition_score,
                preference_score=pref_score,
                nutrition_confidence=nut_res.nutrition_confidence,
                matched_ingredients=ing_res.matched_ingredients,
                missing_ingredients=ing_res.missing_ingredients,
                matched_preferences=matched_prefs,
                per_serving_calories=nut_res.per_serving_calories,
                per_serving_protein=nut_res.per_serving_protein,
            )
            scored_candidates.append(cand)

        # 4. Hybrid ranking
        top_candidates = self.hybrid_ranker.rank_candidates(scored_candidates, top_k=top_k)

        # 5. Generate transparent explanations
        query_recipe_name = self._recipe_names.get(query_recipe_id) if query_recipe_id else None

        result_rows = []
        for rank_idx, cand in enumerate(top_candidates, 1):
            cand.explanation = self.explanation_generator.generate_explanation(
                candidate=cand,
                query_recipe_name=query_recipe_name,
                has_available_ingredients=has_avail,
                total_available=total_avail,
                calorie_target=goals.calorie_target,
                protein_target=goals.protein_target,
            )

            result_rows.append({
                "rank": rank_idx,
                "recipe_id": cand.recipe_id,
                "recipe_name": cand.recipe_name,
                "hybrid_score": cand.hybrid_score,
                "similarity_score": cand.similarity_score,
                "ingredient_match_score": cand.ingredient_match_score,
                "nutrition_score": cand.nutrition_score,
                "preference_score": cand.preference_score,
                "nutrition_confidence": cand.nutrition_confidence,
                "matched_ingredients": ", ".join([i for i in cand.matched_ingredients if i and i.lower() != "nan"]),
                "missing_ingredients": ", ".join([i for i in cand.missing_ingredients[:5] if i and i.lower() != "nan"]),
                "explanation": cand.explanation,
            })

        results_df = pd.DataFrame(result_rows, columns=RECOMMENDATION_COLUMNS)

        if save_results:
            self.config.recommendation_results_path.parent.mkdir(parents=True, exist_ok=True)
            results_df.to_csv(self.config.recommendation_results_path, index=False)

        return results_df
