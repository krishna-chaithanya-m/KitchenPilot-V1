"""Main Recommender Interface for KitchenPilot-V1.

Integrates TF-IDF similarity, canonical ingredient matching, nutrition scoring,
preference filtering, hybrid ranking, and deterministic explainability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd

from src.constraints import ConstraintEngine, ConstraintRequest
from src.ranking.fallback import RankingDispatcher
from src.ranking.features import RankingContext
from src.ranking.xgboost_ranker import XGBoostRanker
from src.personalization.features import UserPersonalizationContext
from src.personalization.scorer import PersonalizationScorer
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
        self.constraint_engine = ConstraintEngine()
        self.xgb_ranker = XGBoostRanker(
            model_path=getattr(self.config, "xgboost_model_path", Path("models/ranking/xgboost_ranker.json")),
            schema_path=getattr(self.config, "xgboost_feature_schema_path", Path("models/ranking/feature_schema.json")),
            metadata_path=getattr(self.config, "xgboost_metadata_path", Path("models/ranking/metadata.json")),
        )
        self.ranking_dispatcher = RankingDispatcher(
            xgboost_ranker=self.xgb_ranker,
            hybrid_ranker=self.hybrid_ranker,
            enabled=getattr(self.config, "xgboost_ranking_enabled", False),
        )
        self.personalization_scorer = PersonalizationScorer(
            weight=getattr(self.config, "personalization_weight", 0.20),
            enabled=getattr(self.config, "personalization_enabled", True),
        )
        self.last_constraint_diagnostics: Optional[Dict[str, Any]] = None
        self.last_constraint_evaluations: Optional[Dict[str, Any]] = None
        self.last_ranked_candidates: List[ScoredCandidate] = []

        self._recipe_names: Dict[str, str] = {}
        self._recipe_metadata: Dict[str, Dict[str, Any]] = {}
        self._load_recipe_names()

        # Load TF-IDF artifacts if available
        if self.config.tfidf_matrix_path.is_file():
            self.tfidf_model.load_artifacts()

        # Stage D: Semantic Retriever (loaded only if explicitly enabled)
        self.semantic_retriever = None
        if getattr(self.config, "semantic_retrieval_enabled", False):
            self._load_semantic_retriever()

    def _load_semantic_retriever(self) -> None:
        """Initialize and load semantic retriever artifacts."""
        from src.retrieval.semantic import SemanticRetriever

        if not self.config.semantic_embeddings_path.is_file():
            raise FileNotFoundError(
                f"Semantic embeddings missing at: {self.config.semantic_embeddings_path}. "
                "Run `python scripts/build_semantic_index.py` first."
            )
        if not self.config.semantic_index_path.is_file():
            raise FileNotFoundError(
                f"Semantic recipe index missing at: {self.config.semantic_index_path}. "
                "Run `python scripts/build_semantic_index.py` first."
            )

        self.semantic_retriever = SemanticRetriever(
            embeddings_path=self.config.semantic_embeddings_path,
            index_path=self.config.semantic_index_path,
            metadata_path=getattr(self.config, "semantic_metadata_path", None),
        )
        self.semantic_retriever.load_artifacts()

    def _load_recipe_names(self) -> None:
        """Load mapping from recipe_id to recipe_name and metadata."""
        if self.config.recipes_path.is_file():
            df = pd.read_csv(self.config.recipes_path)
            for _, row in df.iterrows():
                rid = str(row["recipe_id"]).strip()
                rname = str(row["recipe_name"]).strip() if pd.notna(row["recipe_name"]) else ""
                self._recipe_names[rid] = rname
                ings_raw = str(row.get("ingredients", "")).strip() if pd.notna(row.get("ingredients", "")) else ""
                canon_ings = list(self.ingredient_matcher._recipe_canonical_map.get(rid, set()))
                raw_ings = [i.strip() for i in ings_raw.split(",") if i.strip()]
                all_ings = list(dict.fromkeys(raw_ings + canon_ings))
                self._recipe_metadata[rid] = {
                    "recipe_id": rid,
                    "recipe_name": rname,
                    "cuisine": str(row.get("cuisine", "")).strip() if pd.notna(row.get("cuisine", "")) else "",
                    "region": str(row.get("region", "")).strip() if pd.notna(row.get("region", "")) else "",
                    "meal_type": str(row.get("meal_type", "")).strip() if pd.notna(row.get("meal_type", "")) else "",
                    "category": str(row.get("category", "")).strip() if pd.notna(row.get("category", "")) else "",
                    "ingredients_list": all_ings,
                    "canonical_ingredients": canon_ings,
                }

    def recommend(
        self,
        query_recipe_id: Optional[str] = None,
        available_ingredients: Optional[List[str]] = None,
        user_preferences: Optional[UserPreferences] = None,
        nutrition_goals: Optional[NutritionGoals] = None,
        top_k: int = 10,
        save_results: bool = True,
        constraint_request: Optional[ConstraintRequest] = None,
        user_context: Optional[UserPersonalizationContext] = None,
    ) -> pd.DataFrame:
        """Generate top_k hybrid recipe recommendations.

        Supports:
        - Mode A: Recipe-based recommendation (query_recipe_id)
        - Mode B: Ingredient-based recommendation (available_ingredients)
        - Combined: Both recipe and ingredients + preferences + nutrition goals
        - Stage E: Full constraint engine evaluation (constraint_request)
        """
        if self.tfidf_model.tfidf_matrix is None:
            raise RuntimeError("TF-IDF model artifacts not loaded. Please build the model first.")

        all_rids = self.tfidf_model.recipe_ids
        prefs = user_preferences or UserPreferences()
        goals = nutrition_goals or NutritionGoals()

        if user_context and user_context.disliked_ingredients:
            existing_disliked = set(prefs.disliked_ingredients or [])
            combined_disliked = existing_disliked.union(user_context.disliked_ingredients)
            prefs = UserPreferences(
                vegetarian=prefs.vegetarian,
                vegan=prefs.vegan,
                jain=prefs.jain,
                satvik=prefs.satvik,
                diet_type=prefs.diet_type,
                cuisine=prefs.cuisine,
                region=prefs.region,
                meal_type=prefs.meal_type,
                category=prefs.category,
                excluded_ingredients=prefs.excluded_ingredients,
                required_ingredients=prefs.required_ingredients,
                disliked_ingredients=list(combined_disliked),
            )

        eval_map: Dict[str, Any] = {}
        if constraint_request is not None and getattr(self.config, "constraint_engine_enabled", True):
            # Validate constraint conflicts
            conflicts = self.constraint_engine.validate_request(constraint_request)
            if conflicts:
                raise ValueError(f"Conflicting constraints: {'; '.join(conflicts)}")

            if available_ingredients is None and constraint_request.ingredients.available_ingredients:
                available_ingredients = constraint_request.ingredients.available_ingredients

            if constraint_request.ingredients.required_ingredients:
                combined_req = list(set((prefs.required_ingredients or []) + constraint_request.ingredients.required_ingredients))
                prefs.required_ingredients = combined_req

            pool_rids = [rid for rid in all_rids if not (query_recipe_id and rid == query_recipe_id)]
            candidates_rids, eval_map, diagnostics = self.constraint_engine.filter_candidates(
                pool_rids, constraint_request
            )
            self.last_constraint_diagnostics = diagnostics
            self.last_constraint_evaluations = eval_map
        else:
            # 1. Apply legacy hard dietary and exclusion filters BEFORE ranking
            candidates_rids = []
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
    		disliked_ingredients=prefs.disliked_ingredients,
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

        # 4. Ranking (via Dispatcher: XGBoost when enabled, otherwise HybridRanker)
        tfidf_ranks = {cand.recipe_id: idx for idx, cand in enumerate(sorted(scored_candidates, key=lambda c: -c.similarity_score))}
        pref_ing = []
        if constraint_request and hasattr(constraint_request, "ingredients") and constraint_request.ingredients:
            pref_ing = constraint_request.ingredients.preferred_ingredients or []

        ranking_context = RankingContext(
            query_recipe_id=query_recipe_id,
            available_ingredients=available_ingredients or [],
            required_ingredients=prefs.required_ingredients or [],
            preferred_ingredients=pref_ing,
            calorie_target=goals.calorie_target,
            protein_target=goals.protein_target,
            preferred_cuisine=prefs.cuisine if isinstance(prefs.cuisine, str) else None,
            preferred_region=prefs.region if isinstance(prefs.region, str) else None,
            preferred_meal_type=prefs.meal_type if isinstance(prefs.meal_type, str) else None,
            preferred_category=prefs.category if isinstance(prefs.category, str) else None,
            tfidf_candidates={c.recipe_id: c.similarity_score for c in scored_candidates},
            tfidf_ranks=tfidf_ranks,
            constraint_evaluations=eval_map,
        )

        top_candidates = self.ranking_dispatcher.rank_candidates(
            scored_candidates,
            context=ranking_context,
            top_k=top_k if user_context is None else max(top_k * 2, 50),
        )

        # Stage G: Personalization adjustment and deterministic reranking (applied strictly to eligible candidates)
        top_candidates = self.personalization_scorer.rerank_candidates(
            top_candidates,
            recipe_metadata_map=self._recipe_metadata,
            context=user_context,
            top_k=top_k,
        )
        self.last_ranked_candidates = top_candidates

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
            if cand.recipe_id in eval_map and eval_map[cand.recipe_id].explanation:
                cand.explanation = f"{cand.explanation} [{eval_map[cand.recipe_id].explanation}]"

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

    def recommend_semantic(
        self,
        query: str,
        user_preferences: Optional[UserPreferences] = None,
        nutrition_goals: Optional[NutritionGoals] = None,
        top_k: int = 10,
        candidate_k: int = 50,
        save_results: bool = False,
        constraint_request: Optional[ConstraintRequest] = None,
        user_context: Optional[UserPersonalizationContext] = None,
    ) -> pd.DataFrame:
        """Generate top_k recommendations using dense semantic retrieval (BAAI/bge-small-en-v1.5).

        Evaluates query semantic embedding against precomputed recipe embeddings, applies
        hard dietary/constraint filters, scores candidates on the 4 pillars (using semantic similarity),
        and ranks via the existing HybridRanker.
        """
        if self.semantic_retriever is None:
            self._load_semantic_retriever()

        prefs = user_preferences or UserPreferences()
        goals = nutrition_goals or NutritionGoals()

        if user_context and user_context.disliked_ingredients:
            existing_disliked = set(prefs.disliked_ingredients or [])
            combined_disliked = existing_disliked.union(user_context.disliked_ingredients)
            prefs = UserPreferences(
                vegetarian=prefs.vegetarian,
                vegan=prefs.vegan,
                jain=prefs.jain,
                satvik=prefs.satvik,
                diet_type=prefs.diet_type,
                cuisine=prefs.cuisine,
                region=prefs.region,
                meal_type=prefs.meal_type,
                category=prefs.category,
                excluded_ingredients=prefs.excluded_ingredients,
                required_ingredients=prefs.required_ingredients,
                disliked_ingredients=list(combined_disliked),
            )

        # 1. Semantic retrieval for top candidate_k recipes
        semantic_results = self.semantic_retriever.retrieve(query=query, top_k=candidate_k)
        if not semantic_results:
            return pd.DataFrame(columns=RECOMMENDATION_COLUMNS)

        # 2. Hard filter candidates
        candidate_map = {r.recipe_id: r.score for r in semantic_results}
        eval_map: Dict[str, Any] = {}

        if constraint_request is not None and getattr(self.config, "constraint_engine_enabled", True):
            conflicts = self.constraint_engine.validate_request(constraint_request)
            if conflicts:
                raise ValueError(f"Conflicting constraints: {'; '.join(conflicts)}")

            passing_rids, eval_map, diagnostics = self.constraint_engine.filter_candidates(
                list(candidate_map.keys()), constraint_request
            )
            self.last_constraint_diagnostics = diagnostics
            self.last_constraint_evaluations = eval_map
        else:
            passing_rids = [
                rid
                for rid in candidate_map
                if self.preference_filter.passes_hard_filters(rid, prefs, self.ingredient_matcher)
            ]

        if not passing_rids:
            return pd.DataFrame(columns=RECOMMENDATION_COLUMNS)

        # 3. Score passing candidates across pillars
        scored_candidates: List[ScoredCandidate] = []
        for rid in passing_rids:
            sim_score = candidate_map[rid]
            ing_res = self.ingredient_matcher.match_recipe(
                recipe_id=rid,
                available_ingredients=None,
                required_ingredients=prefs.required_ingredients,
                disliked_ingredients=prefs.disliked_ingredients,
            )
            nut_res = self.nutrition_scorer.score_recipe(rid, goals)
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

        # 4. Rank via ranking dispatcher (XGBoost when enabled, otherwise HybridRanker)
        bge_ranks = {cand.recipe_id: idx for idx, cand in enumerate(sorted(scored_candidates, key=lambda c: -c.similarity_score))}
        pref_ing = []
        if constraint_request and hasattr(constraint_request, "ingredients") and constraint_request.ingredients:
            pref_ing = constraint_request.ingredients.preferred_ingredients or []

        ranking_context = RankingContext(
            query_text=query,
            required_ingredients=prefs.required_ingredients or [],
            preferred_ingredients=pref_ing,
            calorie_target=goals.calorie_target,
            protein_target=goals.protein_target,
            preferred_cuisine=prefs.cuisine if isinstance(prefs.cuisine, str) else None,
            preferred_region=prefs.region if isinstance(prefs.region, str) else None,
            preferred_meal_type=prefs.meal_type if isinstance(prefs.meal_type, str) else None,
            preferred_category=prefs.category if isinstance(prefs.category, str) else None,
            bge_candidates={c.recipe_id: c.similarity_score for c in scored_candidates},
            bge_ranks=bge_ranks,
            constraint_evaluations=eval_map,
        )

        top_candidates = self.ranking_dispatcher.rank_candidates(
            scored_candidates,
            context=ranking_context,
            top_k=top_k if user_context is None else max(top_k * 2, 50),
        )

        # Stage G: Personalization adjustment and deterministic reranking (applied strictly to eligible candidates)
        top_candidates = self.personalization_scorer.rerank_candidates(
            top_candidates,
            recipe_metadata_map=self._recipe_metadata,
            context=user_context,
            top_k=top_k,
        )
        self.last_ranked_candidates = top_candidates

        # 5. Explanations
        result_rows = []
        for rank_idx, cand in enumerate(top_candidates, 1):
            cand.explanation = self.explanation_generator.generate_explanation(
                candidate=cand,
                query_recipe_name=None,
                has_available_ingredients=False,
                total_available=0,
                calorie_target=goals.calorie_target,
                protein_target=goals.protein_target,
            )
            if cand.recipe_id in eval_map and eval_map[cand.recipe_id].explanation:
                cand.explanation = f"{cand.explanation} [{eval_map[cand.recipe_id].explanation}]"

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
