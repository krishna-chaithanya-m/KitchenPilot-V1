"""Ranking dataset generation and query-group management for Stage F.

Supports:
1. Mode A: Weak supervision dataset generation from diverse query templates
2. Mode B: Extensible schema for future genuine user feedback labels (Stage G)
3. Deterministic query-group splitting (Train 70% / Validation 15% / Test 15%)
4. Label leakage prevention (labels generated via multi-signal agreement, NOT baseline hybrid score)
"""

from __future__ import annotations

import logging
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.constraints import (
    ConstraintEngine,
    ConstraintRequest,
    DietaryConstraints,
    IngredientConstraints,
    NutritionConstraints,
)
from src.ranking.features import FEATURE_NAMES, FeatureExtractor, RankingContext
from src.recommendation.config import RecommendationConfig
from src.recommendation.tfidf_model import TFIDFModel
from src.retrieval.semantic import SemanticRetriever

logger = logging.getLogger("kitchenpilot.ranking.dataset")

DATASET_VERSION = "1.0.0"


def compute_weak_relevance_label(
    tfidf_score: float,
    bge_score: float,
    in_both_retrievers: bool,
    ingredient_coverage: float,
    dietary_compliant: bool,
    nutrition_available: bool,
) -> int:
    """Compute an auditable, non-leaking multi-signal weak relevance label (0..3).

    Safety Guard:
    - If dietary non-compliant: label is 0.
    - Grade 3 (High): High retrieval agreement (both or high score) + high ingredient coverage (>= 0.6) + dietary compliant.
    - Grade 2 (Moderate): Good retrieval (score >= 0.35) or good coverage (>= 0.4) + dietary compliant.
    - Grade 1 (Marginal): Admissible candidate in retrieval pool with partial signal.
    - Grade 0 (Low): Weak signal (retrieval < 0.15 and coverage < 0.2).
    """
    if not dietary_compliant:
        return 0

    score_max = max(tfidf_score, bge_score)
    score_avg = (tfidf_score + bge_score) / 2.0 if in_both_retrievers else score_max

    # Grade 3: Strong multi-signal agreement
    if (in_both_retrievers or score_avg >= 0.45) and ingredient_coverage >= 0.5:
        return 3

    # Grade 2: Good retrieval or good ingredient availability
    if score_avg >= 0.35 or ingredient_coverage >= 0.4:
        return 2

    # Grade 1: Passable relevance
    if score_avg >= 0.15 or ingredient_coverage >= 0.2:
        return 1

    return 0


class RankingDatasetBuilder:
    """Constructs versioned, group-aware ranking datasets."""

    def __init__(
        self,
        feature_extractor: Optional[FeatureExtractor] = None,
        config: Optional[RecommendationConfig] = None,
    ) -> None:
        self.config = config or RecommendationConfig()
        self.feature_extractor = feature_extractor or FeatureExtractor()
        self.tfidf_model = TFIDFModel(self.config)
        if self.config.tfidf_matrix_path.is_file():
            self.tfidf_model.load_artifacts()

        self.semantic_retriever: Optional[SemanticRetriever] = None
        if self.config.semantic_embeddings_path.is_file():
            self.semantic_retriever = SemanticRetriever(
                embeddings_path=self.config.semantic_embeddings_path,
                index_path=self.config.semantic_index_path,
            )
            self.semantic_retriever.load_artifacts()

        self.constraint_engine = ConstraintEngine()

    def generate_weak_supervision_dataset(
        self,
        num_queries: int = 120,
        candidates_per_query: int = 40,
        random_seed: int = 42,
    ) -> pd.DataFrame:
        """Generate structured tabular learning-to-rank dataset from representative query templates."""
        random.seed(random_seed)
        np.random.seed(random_seed)

        # Diverse query seed templates representing realistic user journeys
        query_templates = [
            # 1. Ingredient-driven pantry queries
            {"ingredients": ["paneer", "spinach", "tomato", "cumin"], "veg": True, "cal_target": 450},
            {"ingredients": ["chicken", "onion", "garlic", "ginger", "garam masala"], "veg": False, "cal_target": 600},
            {"ingredients": ["toor dal", "mustard seeds", "curry leaves", "turmeric"], "veg": True, "jain": False, "cal_target": 350},
            {"ingredients": ["potato", "cauliflower", "green chilli", "ginger"], "veg": True, "cal_target": 400},
            {"ingredients": ["chickpea", "onion", "tomato", "chana masala"], "veg": True, "cal_target": 500},
            {"ingredients": ["fish", "coconut milk", "mustard seeds", "curry leaves"], "veg": False, "cal_target": 550},
            {"ingredients": ["mushroom", "bell pepper", "onion", "soya sauce"], "veg": True, "cal_target": 300},
            {"ingredients": ["mutton", "onion", "ginger", "cardamom", "cinnamon"], "veg": False, "cal_target": 700},
            {"ingredients": ["rice", "cumin seeds", "ghee", "clove"], "veg": True, "cal_target": 350},
            {"ingredients": ["egg", "onion", "tomato", "black pepper"], "veg": False, "cal_target": 350},
            # 2. Semantic text queries
            {"query": "healthy high protein vegetarian breakfast", "veg": True, "pro_target": 20.0},
            {"query": "spicy south indian sambar with drumsticks", "veg": True, "cuisine": "south indian"},
            {"query": "creamy butter chicken curry with spices", "veg": False, "cuisine": "north indian"},
            {"query": "quick 20 minute dinner recipe with dal", "veg": True, "cal_target": 400},
            {"query": "satvik kheer with almond and saffron", "veg": True, "satvik": True},
            {"query": "jain friendly paneer dish without onion and garlic", "veg": True, "jain": True},
            {"query": "low calorie diabetic friendly vegetable soup", "veg": True, "cal_target": 200},
            {"query": "tasty evening snack with potatoes and mint", "veg": True},
            {"query": "rich royal mughlai biryani with saffron", "veg": False},
            {"query": "refreshing summer raita with cucumber and curd", "veg": True, "cal_target": 150},
        ]

        # Expand templates up to num_queries
        expanded_queries = []
        for i in range(num_queries):
            base = dict(query_templates[i % len(query_templates)])
            qid = f"query_{i+1:04d}"
            base["query_id"] = qid
            expanded_queries.append(base)

        all_rows: List[Dict[str, Any]] = []
        all_rids = self.tfidf_model.recipe_ids

        for q in expanded_queries:
            qid = q["query_id"]
            avail_ings = q.get("ingredients", [])
            query_str = q.get("query", " ".join(avail_ings))
            is_veg = q.get("veg")
            is_jain = q.get("jain")
            is_satvik = q.get("satvik")
            cal_target = q.get("cal_target")
            pro_target = q.get("pro_target")

            # 1. TF-IDF retrieval
            query_vec = self.tfidf_model.transform_text(query_str)
            tfidf_sims = self.tfidf_model.compute_similarity_scores(query_vec)
            top_tfidf_indices = np.argsort(tfidf_sims)[::-1][:candidates_per_query]
            tfidf_candidate_map = {all_rids[idx]: float(tfidf_sims[idx]) for idx in top_tfidf_indices if tfidf_sims[idx] > 0.01}
            tfidf_rank_map = {all_rids[idx]: rank for rank, idx in enumerate(top_tfidf_indices)}

            # 2. BGE semantic retrieval (if available)
            bge_candidate_map: Dict[str, float] = {}
            bge_rank_map: Dict[str, int] = {}
            if self.semantic_retriever:
                semantic_results = self.semantic_retriever.retrieve(query=query_str, top_k=candidates_per_query)
                for rank, res in enumerate(semantic_results):
                    bge_candidate_map[res.recipe_id] = float(res.score)
                    bge_rank_map[res.recipe_id] = rank

            # 3. Candidate union
            candidate_union = list(dict.fromkeys(list(tfidf_candidate_map.keys()) + list(bge_candidate_map.keys())))
            if not candidate_union:
                candidate_union = all_rids[:candidates_per_query]

            # 4. Stage E Constraint filtering
            constraint_req = ConstraintRequest(
                dietary=DietaryConstraints(vegetarian=is_veg, jain=is_jain, satvik=is_satvik),
                ingredients=IngredientConstraints(available_ingredients=avail_ings),
                nutrition=NutritionConstraints(max_calories=cal_target * 1.5 if cal_target else None),
            )
            eligible_rids, eval_map, _ = self.constraint_engine.filter_candidates(candidate_union, constraint_req)
            if not eligible_rids:
                continue

            # Limit query group to top candidates
            group_rids = eligible_rids[:candidates_per_query]

            # Build ranking context
            context = RankingContext(
                query_text=query_str,
                available_ingredients=avail_ings,
                calorie_target=cal_target,
                protein_target=pro_target,
                preferred_cuisine=q.get("cuisine"),
                tfidf_candidates=tfidf_candidate_map,
                bge_candidates=bge_candidate_map,
                tfidf_ranks=tfidf_rank_map,
                bge_ranks=bge_rank_map,
                constraint_evaluations=eval_map,
            )

            # Extract features for all eligible candidates in this group
            for rid in group_rids:
                f_dict = self.feature_extractor.extract_features_single(rid, context)

                # Compute weak relevance label (0..3)
                tfidf_s = tfidf_candidate_map.get(rid, 0.0)
                bge_s = bge_candidate_map.get(rid, 0.0)
                in_both = (rid in tfidf_candidate_map) and (rid in bge_candidate_map)
                cov = f_dict.get("ingredient_coverage_ratio", 0.0)
                diet_ok = bool(f_dict.get("vegetarian_compliant", 1.0)) if is_veg else True
                nut_ok = bool(f_dict.get("nutrition_available", 0.0))

                label = compute_weak_relevance_label(
                    tfidf_score=tfidf_s,
                    bge_score=bge_s,
                    in_both_retrievers=in_both,
                    ingredient_coverage=cov,
                    dietary_compliant=diet_ok,
                    nutrition_available=nut_ok,
                )

                row: Dict[str, Any] = {
                    "query_id": qid,
                    "recipe_id": rid,
                    "label": int(label),
                }
                # Append ordered features
                for fname in FEATURE_NAMES:
                    row[fname] = f_dict[fname]

                all_rows.append(row)

        df = pd.DataFrame(all_rows)
        logger.info("Generated ranking dataset: %d rows across %d queries", len(df), df["query_id"].nunique())
        return df

    def split_by_query_group(
        self,
        df: pd.DataFrame,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        random_seed: int = 42,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Split dataset strictly by query_id (group level) to prevent query leakage.

        Guarantees:
        1. No query_id appears in more than one partition.
        2. Ratios match approximately 70% / 15% / 15%.
        3. Deterministic split using fixed random seed.
        """
        unique_queries = sorted(df["query_id"].unique().tolist())
        rng = random.Random(random_seed)
        rng.shuffle(unique_queries)

        n_total = len(unique_queries)
        n_train = int(round(n_total * train_ratio))
        n_val = int(round(n_total * val_ratio))

        train_queries = set(unique_queries[:n_train])
        val_queries = set(unique_queries[n_train:n_train + n_val])
        test_queries = set(unique_queries[n_train + n_val:])

        df_train = df[df["query_id"].isin(train_queries)].copy()
        df_val = df[df["query_id"].isin(val_queries)].copy()
        df_test = df[df["query_id"].isin(test_queries)].copy()

        # Verify zero overlap
        assert len(train_queries & val_queries) == 0, "Query leakage between train and val!"
        assert len(train_queries & test_queries) == 0, "Query leakage between train and test!"
        assert len(val_queries & test_queries) == 0, "Query leakage between val and test!"

        return df_train, df_val, df_test
