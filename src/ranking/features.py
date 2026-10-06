"""Feature engineering pipeline for Stage F XGBoost Learning-to-Rank.

Extracts structured, stable, deterministic numeric feature vectors across:
1. Retrieval signals (TF-IDF similarity, BGE semantic similarity, reciprocal ranks, agreement)
2. Ingredient signals (match counts, coverage ratios, pantry availability, preferred/canonical matches)
3. Nutrition signals (calorie/protein target distance, per-serving macronutrients, completeness)
4. Dietary signals (vegetarian, vegan, Jain, Satvik compliance)
5. Recipe metadata signals (cuisine match, region match, meal type match, preparation/cook time)
6. Hard constraint safety guard (always 0.0 since violations are eliminated prior to ranking)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger("kitchenpilot.ranking.features")

# Canonical feature list and fixed ordering (feature schema v1.0.0)
FEATURE_SCHEMA_VERSION = "1.0.0"
FEATURE_NAMES: List[str] = [
    # 1. Retrieval signals
    "retrieval_tfidf_score",
    "retrieval_bge_score",
    "retrieval_tfidf_rr",       # Reciprocal rank: 1 / (rank + 1)
    "retrieval_bge_rr",         # Reciprocal rank: 1 / (rank + 1)
    "retrieval_both",           # Indicator: appears in both candidate sets
    # 2. Ingredient signals
    "ingredient_match_count",
    "ingredient_total_count",
    "ingredient_coverage_ratio",
    "pantry_coverage_ratio",
    "required_ingredient_count",
    "preferred_ingredient_count",
    "canonical_match_count",
    # 3. Nutrition signals
    "calorie_target_distance",
    "protein_target_distance",
    "per_serving_calories",
    "per_serving_protein_g",
    "per_serving_carbs_g",
    "per_serving_fat_g",
    "per_serving_fiber_g",
    "nutrition_available",
    # 4. Dietary compliance signals
    "vegetarian_compliant",
    "vegan_compliant",
    "jain_compliant",
    "satvik_compliant",
    # 5. Recipe metadata signals
    "cuisine_match",
    "region_match",
    "meal_type_match",
    "category_match",
    "total_time_min",
    # 6. Safety invariant feature
    "hard_constraint_violation",  # Must be 0.0 for all admissible candidates
]


@dataclass
class RankingContext:
    """Request-level context required for candidate feature extraction."""
    query_recipe_id: Optional[str] = None
    query_text: Optional[str] = None
    available_ingredients: List[str] = field(default_factory=list)
    required_ingredients: List[str] = field(default_factory=list)
    preferred_ingredients: List[str] = field(default_factory=list)
    calorie_target: Optional[float] = None
    protein_target: Optional[float] = None
    preferred_cuisine: Optional[str] = None
    preferred_region: Optional[str] = None
    preferred_meal_type: Optional[str] = None
    preferred_category: Optional[str] = None
    # Retrieval candidate pools: recipe_id -> score
    tfidf_candidates: Dict[str, float] = field(default_factory=dict)
    bge_candidates: Dict[str, float] = field(default_factory=dict)
    # Precomputed rank maps: recipe_id -> 0-based rank
    tfidf_ranks: Dict[str, int] = field(default_factory=dict)
    bge_ranks: Dict[str, int] = field(default_factory=dict)
    # Constraint evaluation records from Stage E
    constraint_evaluations: Dict[str, Any] = field(default_factory=dict)


class FeatureExtractor:
    """Deterministic feature extractor generating stable tabular feature matrices."""

    def __init__(
        self,
        recipes_path: Path = Path("data/processed/recipes.csv"),
        recipe_nutrition_path: Path = Path("data/processed/recipe_nutrition.csv"),
        linked_ingredients_path: Path = Path("data/processed/recipe_ingredients_linked.csv"),
    ) -> None:
        self.recipes_path = recipes_path
        self.recipe_nutrition_path = recipe_nutrition_path
        self.linked_ingredients_path = linked_ingredients_path
        self.feature_names = list(FEATURE_NAMES)
        self.feature_schema_version = FEATURE_SCHEMA_VERSION

        # In-memory caches for fast feature assembly
        self._recipes_metadata: Dict[str, Dict[str, Any]] = {}
        self._nutrition_data: Dict[str, Dict[str, Optional[float]]] = {}
        self._recipe_ingredients: Dict[str, List[str]] = {}
        self._recipe_canonical_names: Dict[str, set] = {}

        self._load_metadata()

    def _load_metadata(self) -> None:
        """Load and cache static recipe profiles."""
        if self.recipes_path.is_file():
            df_rec = pd.read_csv(self.recipes_path, low_memory=False)
            for _, row in df_rec.iterrows():
                rid = str(row["recipe_id"]).strip()
                self._recipes_metadata[rid] = {
                    "cuisine": str(row.get("cuisine", "")).strip().lower(),
                    "region": str(row.get("region", "")).strip().lower(),
                    "meal_type": str(row.get("meal_type", "")).strip().lower(),
                    "category": str(row.get("category", "")).strip().lower(),
                    "vegetarian": bool(row.get("vegetarian")) if pd.notna(row.get("vegetarian")) else False,
                    "vegan": bool(row.get("vegan")) if pd.notna(row.get("vegan")) else False,
                    "jain": bool(row.get("jain")) if pd.notna(row.get("jain")) else False,
                    "satvik": bool(row.get("satvik")) if pd.notna(row.get("satvik")) else False,
                    "total_time_min": float(row["total_time_min"]) if pd.notna(row.get("total_time_min")) else 30.0,
                }

        if self.recipe_nutrition_path.is_file():
            df_nut = pd.read_csv(self.recipe_nutrition_path, low_memory=False)
            for _, row in df_nut.iterrows():
                rid = str(row["recipe_id"]).strip()
                cal = float(row["per_serving_calories_kcal"]) if pd.notna(row.get("per_serving_calories_kcal")) else None
                self._nutrition_data[rid] = {
                    "calories": cal,
                    "protein": float(row["per_serving_protein_g"]) if pd.notna(row.get("per_serving_protein_g")) else None,
                    "carbs": float(row["per_serving_carbs_g"]) if pd.notna(row.get("per_serving_carbs_g")) else None,
                    "fat": float(row["per_serving_fat_g"]) if pd.notna(row.get("per_serving_fat_g")) else None,
                    "fiber": float(row["per_serving_fiber_g"]) if pd.notna(row.get("per_serving_fiber_g")) else None,
                    "available": 1.0 if cal is not None else 0.0,
                }

        if self.linked_ingredients_path.is_file():
            df_ing = pd.read_csv(self.linked_ingredients_path, low_memory=False)
            for _, row in df_ing.iterrows():
                rid = str(row["recipe_id"]).strip()
                ing = str(row.get("ingredient", "")).strip().lower()
                cname = str(row.get("canonical_ingredient", "")).strip().lower()
                if rid not in self._recipe_ingredients:
                    self._recipe_ingredients[rid] = []
                    self._recipe_canonical_names[rid] = set()
                if ing and ing != "nan":
                    self._recipe_ingredients[rid].append(ing)
                if cname and cname != "nan":
                    self._recipe_canonical_names[rid].add(cname)

    def extract_features_single(
        self,
        recipe_id: str,
        context: RankingContext,
    ) -> Dict[str, float]:
        """Extract a single candidate's feature dictionary strictly following FEATURE_NAMES."""
        meta = self._recipes_metadata.get(recipe_id, {})
        nut = self._nutrition_data.get(recipe_id, {})
        clean_ings = self._recipe_ingredients.get(recipe_id, [])
        canon_ings = self._recipe_canonical_names.get(recipe_id, set())

        # 1. Retrieval Features
        tfidf_score = float(context.tfidf_candidates.get(recipe_id, 0.0))
        bge_score = float(context.bge_candidates.get(recipe_id, 0.0))
        in_tfidf = recipe_id in context.tfidf_candidates
        in_bge = recipe_id in context.bge_candidates

        tfidf_rank = context.tfidf_ranks.get(recipe_id)
        tfidf_rr = 1.0 / (float(tfidf_rank) + 1.0) if tfidf_rank is not None else 0.0

        bge_rank = context.bge_ranks.get(recipe_id)
        bge_rr = 1.0 / (float(bge_rank) + 1.0) if bge_rank is not None else 0.0

        retrieval_both = 1.0 if (in_tfidf and in_bge) else 0.0

        # 2. Ingredient Features
        total_ings = max(1, len(clean_ings))
        matched_avail_count = 0
        canonical_matches = 0
        if context.available_ingredients:
            avail_low = [a.lower().strip() for a in context.available_ingredients if a.strip()]
            for a in avail_low:
                if any(a in ing for ing in clean_ings):
                    matched_avail_count += 1
                if a in canon_ings:
                    canonical_matches += 1

        coverage_ratio = float(matched_avail_count) / float(total_ings)

        # Pantry coverage from Stage E evaluation if available
        ev = context.constraint_evaluations.get(recipe_id)
        pantry_cov = 0.0
        if ev and hasattr(ev, "pantry_metrics") and ev.pantry_metrics:
            pantry_cov = float(ev.pantry_metrics.coverage_ratio)
        else:
            pantry_cov = coverage_ratio

        # Required ingredients match count
        req_match = 0
        if context.required_ingredients:
            req_low = [r.lower().strip() for r in context.required_ingredients if r.strip()]
            req_match = sum(1 for r in req_low if any(r in ing for ing in clean_ings))

        # Preferred ingredients match count
        pref_match = 0
        if context.preferred_ingredients:
            pref_low = [p.lower().strip() for p in context.preferred_ingredients if p.strip()]
            pref_match = sum(1 for p in pref_low if any(p in ing for ing in clean_ings))

        # 3. Nutrition Features
        cal = nut.get("calories")
        pro = nut.get("protein")
        carbs = nut.get("carbs")
        fat = nut.get("fat")
        fiber = nut.get("fiber")
        nut_avail = nut.get("available", 0.0)

        cal_dist = 0.0
        if context.calorie_target is not None and cal is not None and cal > 0:
            cal_dist = abs(cal - context.calorie_target) / 500.0

        pro_dist = 0.0
        if context.protein_target is not None and pro is not None and pro > 0:
            pro_dist = abs(pro - context.protein_target) / 20.0

        # 4. Dietary Compliance Features
        veg_comp = 1.0 if meta.get("vegetarian", False) else 0.0
        vegan_comp = 1.0 if meta.get("vegan", False) else 0.0
        jain_comp = 1.0 if meta.get("jain", False) else 0.0
        satvik_comp = 1.0 if meta.get("satvik", False) else 0.0

        # If Stage E evaluation evaluated dietary statuses, update with authoritative result
        if ev and hasattr(ev, "dietary_results") and ev.dietary_results:
            d_res = ev.dietary_results
            if "vegetarian" in d_res:
                veg_comp = 1.0 if getattr(d_res["vegetarian"], "value", str(d_res["vegetarian"])) == "COMPLIANT" else 0.0
            if "vegan" in d_res:
                vegan_comp = 1.0 if getattr(d_res["vegan"], "value", str(d_res["vegan"])) == "COMPLIANT" else 0.0
            if "jain" in d_res:
                jain_comp = 1.0 if getattr(d_res["jain"], "value", str(d_res["jain"])) == "COMPLIANT" else 0.0
            if "satvik" in d_res:
                satvik_comp = 1.0 if getattr(d_res["satvik"], "value", str(d_res["satvik"])) == "COMPLIANT" else 0.0

        # 5. Metadata Matches
        cuisine_match = 0.0
        if context.preferred_cuisine and meta.get("cuisine"):
            cuisine_match = 1.0 if context.preferred_cuisine.lower() in meta["cuisine"] else 0.0

        region_match = 0.0
        if context.preferred_region and meta.get("region"):
            region_match = 1.0 if context.preferred_region.lower() in meta["region"] else 0.0

        meal_match = 0.0
        if context.preferred_meal_type and meta.get("meal_type"):
            meal_match = 1.0 if context.preferred_meal_type.lower() in meta["meal_type"] else 0.0

        cat_match = 0.0
        if context.preferred_category and meta.get("category"):
            cat_match = 1.0 if context.preferred_category.lower() in meta["category"] else 0.0

        tot_time = meta.get("total_time_min", 30.0)

        # 6. Safety Invariant: Candidates entering ranker are already validated
        hard_violation = 0.0

        return {
            "retrieval_tfidf_score": round(tfidf_score, 4),
            "retrieval_bge_score": round(bge_score, 4),
            "retrieval_tfidf_rr": round(tfidf_rr, 4),
            "retrieval_bge_rr": round(bge_rr, 4),
            "retrieval_both": retrieval_both,
            "ingredient_match_count": float(matched_avail_count),
            "ingredient_total_count": float(total_ings),
            "ingredient_coverage_ratio": round(coverage_ratio, 4),
            "pantry_coverage_ratio": round(pantry_cov, 4),
            "required_ingredient_count": float(req_match),
            "preferred_ingredient_count": float(pref_match),
            "canonical_match_count": float(canonical_matches),
            "calorie_target_distance": round(cal_dist, 4),
            "protein_target_distance": round(pro_dist, 4),
            "per_serving_calories": float(cal) if cal is not None else 0.0,
            "per_serving_protein_g": float(pro) if pro is not None else 0.0,
            "per_serving_carbs_g": float(carbs) if carbs is not None else 0.0,
            "per_serving_fat_g": float(fat) if fat is not None else 0.0,
            "per_serving_fiber_g": float(fiber) if fiber is not None else 0.0,
            "nutrition_available": nut_avail,
            "vegetarian_compliant": veg_comp,
            "vegan_compliant": vegan_comp,
            "jain_compliant": jain_comp,
            "satvik_compliant": satvik_comp,
            "cuisine_match": cuisine_match,
            "region_match": region_match,
            "meal_type_match": meal_match,
            "category_match": cat_match,
            "total_time_min": float(tot_time),
            "hard_constraint_violation": hard_violation,
        }

    def extract_features(
        self,
        candidate_recipe_ids: Sequence[str],
        context: RankingContext,
    ) -> Tuple[np.ndarray, List[Dict[str, float]]]:
        """Extract ordered feature matrix (N x M) and feature dictionaries for candidates.

        Returns:
            (feature_matrix_ndarray, list_of_feature_dicts)
        """
        rows: List[Dict[str, float]] = []
        matrix_rows: List[List[float]] = []

        for rid in candidate_recipe_ids:
            f_dict = self.extract_features_single(rid, context)
            rows.append(f_dict)
            # Maintain strict schema ordering
            matrix_rows.append([f_dict[name] for name in self.feature_names])

        if not matrix_rows:
            return np.empty((0, len(self.feature_names)), dtype=np.float32), []

        matrix = np.array(matrix_rows, dtype=np.float32)
        return matrix, rows

    def save_feature_schema(self, output_path: Path) -> None:
        """Export stable feature schema metadata artifact."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        schema_meta = {
            "feature_schema_version": self.feature_schema_version,
            "feature_count": len(self.feature_names),
            "feature_names": self.feature_names,
            "feature_order": {name: idx for idx, name in enumerate(self.feature_names)},
            "description": "Stage F Learning-to-Rank stable feature schema for KitchenPilot-V1",
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(schema_meta, f, indent=2)
        logger.info("Saved feature schema (%d features) to %s", len(self.feature_names), output_path)
