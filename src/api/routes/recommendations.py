"""Recommendation Route Endpoints for KitchenPilot-V1 API."""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.config import RECOMMENDATION_HISTORY_ENABLED
from src.api.dependencies import (
    RecipeStore,
    get_db,
    get_optional_current_user,
    get_recipe_store,
    get_recommender,
)
from src.api.middleware import metrics_collector
from src.api.routes.recipes import _format_recommendations_from_df
from src.personalization.features import UserPersonalizationContext
from src.personalization.history import generate_session_id, log_recommendation_events
from src.personalization.models import UserModel
from src.personalization.service import PersonalizationService
from src.api.schemas import (
    IngredientRecommendRequest,
    NutritionGoalsRequest,
    RecommendationResponse,
    RecommendRequest,
    SemanticRecommendRequest,
    UserPreferencesRequest,
)
from src.constraints import (
    AllergenConstraints,
    ConstraintRequest,
    DietaryConstraints,
    IngredientConstraints,
    NutritionConstraints,
    SoftPreferenceConstraints,
    build_zero_result_diagnostics,
)
from src.recommendation.nutrition_scorer import NutritionGoals
from src.recommendation.preference_filter import UserPreferences
from src.recommendation.recommender import KitchenPilotRecommender

router = APIRouter(prefix="/api/v1/recommend", tags=["Recommendations"])


def _to_engine_preferences(req_prefs: Optional[UserPreferencesRequest]) -> Optional[UserPreferences]:
    """Convert API preferences request schema to recommendation engine dataclass."""
    if req_prefs is None:
        return None
    return UserPreferences(
        vegetarian=req_prefs.vegetarian,
        vegan=req_prefs.vegan,
        jain=req_prefs.jain,
        satvik=req_prefs.satvik,
        diet_type=req_prefs.diet_type,
        cuisine=req_prefs.cuisine,
        region=req_prefs.region,
        meal_type=req_prefs.meal_type,
        category=req_prefs.category,
        excluded_ingredients=req_prefs.excluded_ingredients or [],
        required_ingredients=req_prefs.required_ingredients or [],
    )


def _to_engine_goals(req_goals: Optional[NutritionGoalsRequest]) -> Optional[NutritionGoals]:
    """Convert API nutrition goals request schema to recommendation engine dataclass."""
    if req_goals is None:
        return None
    return NutritionGoals(
        calorie_target=req_goals.calorie_target,
        max_calories=req_goals.max_calories,
        min_protein=req_goals.min_protein,
        max_fat=req_goals.max_fat,
        max_carbs=req_goals.max_carbs,
        min_fiber=req_goals.min_fiber,
    )


def _build_constraint_request(
    request: Union[RecommendRequest, IngredientRecommendRequest, SemanticRecommendRequest],
    user_context: Optional[Any] = None,
) -> Optional[ConstraintRequest]:
    """Build a ConstraintRequest if any Stage E constraint fields, preferences, or context are present."""
    has_user_prefs = getattr(request, "user_preferences", None) is not None
    has_nut_goals = getattr(request, "nutrition_goals", None) is not None
    has_context_diet = (
        user_context is not None
        and any([
            getattr(user_context, "vegetarian", False),
            getattr(user_context, "vegan", False),
            getattr(user_context, "jain", False),
            getattr(user_context, "satvik", False),
        ])
    )

    has_stage_e = any([
        getattr(request, "dietary_constraints", None) is not None,
        getattr(request, "allergen_constraints", None) is not None,
        getattr(request, "ingredient_constraints", None) is not None,
        getattr(request, "nutrition_constraints", None) is not None,
        getattr(request, "excluded_allergens", None) is not None,
        getattr(request, "excluded_ingredients", None) is not None,
        getattr(request, "required_ingredients", None) is not None,
        getattr(request, "preferred_ingredients", None) is not None,
        getattr(request, "require_all_ingredients", None) is not None,
        has_user_prefs,
        has_nut_goals,
        has_context_diet,
    ])

    if not has_stage_e:
        return None

    # Dietary
    diet = DietaryConstraints()
    dc = getattr(request, "dietary_constraints", None)
    up = getattr(request, "user_preferences", None)

    for field in ("vegetarian", "vegan", "jain", "satvik"):
        val = None
        if dc is not None and getattr(dc, field, None) is not None:
            val = getattr(dc, field)
        elif up is not None and getattr(up, field, None) is not None:
            val = getattr(up, field)
        elif user_context is not None and getattr(user_context, field, None) is not None:
            val = getattr(user_context, field)
        setattr(diet, field, val)

    # Allergens
    allergens_list = []
    if getattr(request, "allergen_constraints", None) is not None:
        allergens_list.extend(request.allergen_constraints.excluded_allergens or [])
    if getattr(request, "excluded_allergens", None) is not None:
        allergens_list.extend(request.excluded_allergens or [])
    allg = AllergenConstraints(excluded_allergens=list(dict.fromkeys(allergens_list)))

    # Ingredients
    exc_ing = []
    req_ing = []
    pref_ing = []
    avail_ing = []
    req_all = False

    if getattr(request, "ingredient_constraints", None) is not None:
        ic = request.ingredient_constraints
        exc_ing.extend(ic.excluded_ingredients or [])
        req_ing.extend(ic.required_ingredients or [])
        pref_ing.extend(ic.preferred_ingredients or [])
        avail_ing.extend(ic.available_ingredients or [])
        req_all = ic.require_all_ingredients

    if getattr(request, "excluded_ingredients", None) is not None:
        exc_ing.extend(request.excluded_ingredients or [])
    elif getattr(request, "user_preferences", None) and request.user_preferences.excluded_ingredients:
        exc_ing.extend(request.user_preferences.excluded_ingredients)

    if getattr(request, "required_ingredients", None) is not None:
        req_ing.extend(request.required_ingredients or [])
    elif getattr(request, "user_preferences", None) and request.user_preferences.required_ingredients:
        req_ing.extend(request.user_preferences.required_ingredients)

    if getattr(request, "preferred_ingredients", None) is not None:
        pref_ing.extend(request.preferred_ingredients or [])

    if getattr(request, "require_all_ingredients", None) is not None:
        req_all = bool(request.require_all_ingredients)

    if getattr(request, "available_ingredients", None) is not None:
        avail_ing.extend(request.available_ingredients or [])
    if getattr(request, "ingredients", None) is not None:
        avail_ing.extend(request.ingredients or [])

    ing_c = IngredientConstraints(
        excluded_ingredients=list(dict.fromkeys(exc_ing)),
        required_ingredients=list(dict.fromkeys(req_ing)),
        preferred_ingredients=list(dict.fromkeys(pref_ing)),
        available_ingredients=list(dict.fromkeys(avail_ing)),
        require_all_ingredients=req_all,
    )

    # Nutrition
    nut_c = NutritionConstraints()
    if getattr(request, "nutrition_constraints", None) is not None:
        nc = request.nutrition_constraints
        nut_c.min_calories = nc.min_calories
        nut_c.max_calories = nc.max_calories
        nut_c.min_protein_g = nc.min_protein_g
        nut_c.max_protein_g = nc.max_protein_g
        nut_c.min_carbs_g = nc.min_carbs_g
        nut_c.max_carbs_g = nc.max_carbs_g
        nut_c.min_fat_g = nc.min_fat_g
        nut_c.max_fat_g = nc.max_fat_g
        nut_c.min_fiber_g = nc.min_fiber_g
        nut_c.max_fiber_g = nc.max_fiber_g
    elif getattr(request, "nutrition_goals", None) is not None:
        ng = request.nutrition_goals
        nut_c.max_calories = ng.max_calories
        nut_c.min_protein_g = ng.min_protein
        nut_c.max_fat_g = ng.max_fat
        nut_c.max_carbs_g = ng.max_carbs
        nut_c.min_fiber_g = ng.min_fiber

    # Soft Preferences
    soft_p = SoftPreferenceConstraints()
    if getattr(request, "user_preferences", None) is not None:
        up = request.user_preferences
        soft_p.cuisine = up.cuisine
        soft_p.region = up.region
        soft_p.meal_type = up.meal_type
        soft_p.category = up.category

    return ConstraintRequest(
        dietary=diet,
        allergens=allg,
        ingredients=ing_c,
        nutrition=nut_c,
        preferences=soft_p,
    )


@router.post(
    "",
    response_model=RecommendationResponse,
    summary="Generate Hybrid Recommendations",
    description="Main recommendation endpoint supporting recipe-similarity mode, ingredient-matching mode, dietary hard filtering, nutrition targeting, Stage E constraints, and hybrid ranking.",
)
def generate_recommendations(
    request: RecommendRequest,
    store: RecipeStore = Depends(get_recipe_store),
    recommender: KitchenPilotRecommender = Depends(get_recommender),
    current_user: Optional[UserModel] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    """Execute hybrid recommendation pipeline with optional user personalization."""
    if request.query_recipe_id and not store.exists(request.query_recipe_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Query recipe not found: {request.query_recipe_id}",
        )

    # Stage G: Compile user context if authenticated
    user_context = None
    if current_user:
        user_context = PersonalizationService.get_user_context(db, current_user.id)

    constraint_req = _build_constraint_request(request, user_context=user_context)
    if constraint_req is not None:
        conflicts = recommender.constraint_engine.validate_request(constraint_req)
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Constraint conflict: {'; '.join(conflicts)}",
            )

    prefs = _to_engine_preferences(request.user_preferences)
    goals = _to_engine_goals(request.nutrition_goals)

    # Inherit dietary preferences from profile if not explicitly specified in request
    if user_context and request.user_preferences is None and (
        user_context.vegetarian or user_context.vegan or user_context.jain or user_context.satvik
    ):
        prefs = UserPreferences(
            vegetarian=user_context.vegetarian,
            vegan=user_context.vegan,
            jain=user_context.jain,
            satvik=user_context.satvik,
            disliked_ingredients=list(user_context.disliked_ingredients or []),
        )

    results_df = recommender.recommend(
        query_recipe_id=request.query_recipe_id,
        available_ingredients=request.available_ingredients,
        user_preferences=prefs,
        nutrition_goals=goals,
        top_k=request.top_k,
        save_results=False,
        constraint_request=constraint_req,
        user_context=user_context,
    )
    items = _format_recommendations_from_df(results_df)

    # Record mode metrics
    mode_name = "recipe_similarity" if request.query_recipe_id else ("ingredient_matching" if request.available_ingredients else "preferences_only")
    if user_context is not None:
        mode_name += "_personalized"
    metrics_collector.record_recommendation(mode_name)

    cand_count = (
        recommender.last_constraint_diagnostics.get("total_candidates", 6871)
        if recommender.last_constraint_diagnostics
        else 6871
    )
    metrics_collector.record_recommendation_event(
        success=True,
        zero_results=len(items) == 0,
        candidates_retrieved=cand_count,
        returned_count=len(items),
    )
    if len(items) > 0:
        metrics_collector.record_impression(len(items))

    query_meta: Dict[str, Any] = {
        "query_recipe_id": request.query_recipe_id,
        "available_ingredients": request.available_ingredients or [],
        "user_preferences": request.user_preferences.model_dump() if request.user_preferences else {},
        "nutrition_goals": request.nutrition_goals.model_dump() if request.nutrition_goals else {},
        "top_k": request.top_k,
        "user_id": current_user.id if current_user else None,
        "personalization_applied": user_context is not None,
    }

    # Audit log recommendation events for authenticated users
    if current_user and RECOMMENDATION_HISTORY_ENABLED and recommender.last_ranked_candidates:
        session_id = generate_session_id()
        ranking_method = "xgboost" if getattr(recommender.ranking_dispatcher, "enabled", False) else "hybrid"
        model_version = "xgb_ranker_v0.1.0" if getattr(recommender.ranking_dispatcher, "enabled", False) else "hybrid_v1"
        log_recommendation_events(
            db=db,
            user_id=current_user.id,
            session_id=session_id,
            ranked_candidates=recommender.last_ranked_candidates,
            ranking_method=ranking_method,
            model_version=model_version,
            personalization_applied=True,
            context_metadata=query_meta,
        )

    diagnostics = recommender.last_constraint_diagnostics if constraint_req else None
    message = None
    if len(items) == 0:
        if constraint_req is not None:
            diagnostics = build_zero_result_diagnostics(
                raw_diagnostics=recommender.last_constraint_diagnostics,
                constraint_request=constraint_req,
                total_pool_size=len(store.recipes_df) if hasattr(store, "recipes_df") else 6871,
            )
            message = "No recipes satisfy all specified hard constraints."
        else:
            diagnostics = build_zero_result_diagnostics(
                raw_diagnostics={"total_candidates": 0, "rejected_count": 0},
                constraint_request=None,
                total_pool_size=len(store.recipes_df) if hasattr(store, "recipes_df") else 6871,
            )
            message = "No recipes matched your query criteria."

    return RecommendationResponse(
        query=query_meta,
        count=len(items),
        recommendations=items,
        message=message,
        diagnostics=diagnostics,
    )


@router.post(
    "/by-ingredients",
    response_model=RecommendationResponse,
    summary="Ingredient-Based Recommendations",
    description="Pantry/ingredient focused recommendation endpoint to find recipes matching available ingredients with preference, Stage E constraints, and nutrition filtering.",
)
def recommend_by_ingredients(
    request: IngredientRecommendRequest,
    recommender: KitchenPilotRecommender = Depends(get_recommender),
    current_user: Optional[UserModel] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    """Execute ingredient-focused recommendation with optional user personalization."""
    # Stage G: Compile user context if authenticated
    user_context = None
    if current_user:
        user_context = PersonalizationService.get_user_context(db, current_user.id)

    constraint_req = _build_constraint_request(request, user_context=user_context)
    if constraint_req is not None:
        conflicts = recommender.constraint_engine.validate_request(constraint_req)
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Constraint conflict: {'; '.join(conflicts)}",
            )

    prefs = _to_engine_preferences(request.user_preferences)
    goals = _to_engine_goals(request.nutrition_goals)

    if user_context and request.user_preferences is None and (
        user_context.vegetarian or user_context.vegan or user_context.jain or user_context.satvik
    ):
        prefs = UserPreferences(
            vegetarian=user_context.vegetarian,
            vegan=user_context.vegan,
            jain=user_context.jain,
            satvik=user_context.satvik,
            disliked_ingredients=list(user_context.disliked_ingredients or []),
        )

    results_df = recommender.recommend(
        available_ingredients=request.ingredients,
        user_preferences=prefs,
        nutrition_goals=goals,
        top_k=request.top_k,
        save_results=False,
        constraint_request=constraint_req,
        user_context=user_context,
    )
    items = _format_recommendations_from_df(results_df)

    cand_count = (
        recommender.last_constraint_diagnostics.get("total_candidates", 6871)
        if recommender.last_constraint_diagnostics
        else 6871
    )
    metrics_collector.record_recommendation("by_ingredients")
    metrics_collector.record_recommendation_event(
        success=True,
        zero_results=len(items) == 0,
        candidates_retrieved=cand_count,
        returned_count=len(items),
    )
    if len(items) > 0:
        metrics_collector.record_impression(len(items))

    query_meta: Dict[str, Any] = {
        "ingredients": request.ingredients,
        "user_preferences": request.user_preferences.model_dump() if request.user_preferences else {},
        "nutrition_goals": request.nutrition_goals.model_dump() if request.nutrition_goals else {},
        "top_k": request.top_k,
        "mode": "ingredient_based",
        "user_id": current_user.id if current_user else None,
        "personalization_applied": user_context is not None,
    }

    if current_user and RECOMMENDATION_HISTORY_ENABLED and recommender.last_ranked_candidates:
        session_id = generate_session_id()
        ranking_method = "xgboost" if getattr(recommender.ranking_dispatcher, "enabled", False) else "hybrid"
        model_version = "xgb_ranker_v0.1.0" if getattr(recommender.ranking_dispatcher, "enabled", False) else "hybrid_v1"
        log_recommendation_events(
            db=db,
            user_id=current_user.id,
            session_id=session_id,
            ranked_candidates=recommender.last_ranked_candidates,
            ranking_method=ranking_method,
            model_version=model_version,
            personalization_applied=True,
            context_metadata=query_meta,
        )

    diagnostics = recommender.last_constraint_diagnostics if constraint_req else None
    message = None
    if len(items) == 0:
        if constraint_req is not None:
            diagnostics = build_zero_result_diagnostics(
                raw_diagnostics=recommender.last_constraint_diagnostics,
                constraint_request=constraint_req,
                total_pool_size=6871,
            )
            message = "No recipes satisfy all specified hard constraints."
        else:
            diagnostics = build_zero_result_diagnostics(
                raw_diagnostics={"total_candidates": 0, "rejected_count": 0},
                constraint_request=None,
                total_pool_size=6871,
            )
            message = "No recipes matched your query criteria."

    return RecommendationResponse(
        query=query_meta,
        count=len(items),
        recommendations=items,
        message=message,
        diagnostics=diagnostics,
    )


@router.post(
    "/semantic",
    response_model=RecommendationResponse,
    summary="Semantic Natural Language Recommendations",
    description="Dense semantic retrieval endpoint using BAAI/bge-small-en-v1.5 embeddings for natural language queries, with preference filtering, Stage E constraints, and nutrition targeting.",
)
def recommend_semantic(
    request: SemanticRecommendRequest,
    recommender: KitchenPilotRecommender = Depends(get_recommender),
    current_user: Optional[UserModel] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    """Execute dense semantic recommendation pipeline with optional user personalization."""
    user_context = None
    if current_user:
        user_context = PersonalizationService.get_user_context(db, current_user.id)

    constraint_req = _build_constraint_request(request, user_context=user_context)
    if constraint_req is not None:
        conflicts = recommender.constraint_engine.validate_request(constraint_req)
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Constraint conflict: {'; '.join(conflicts)}",
            )

    prefs = _to_engine_preferences(request.user_preferences)
    goals = _to_engine_goals(request.nutrition_goals)

    if user_context and request.user_preferences is None and (
        user_context.vegetarian or user_context.vegan or user_context.jain or user_context.satvik
    ):
        prefs = UserPreferences(
            vegetarian=user_context.vegetarian,
            vegan=user_context.vegan,
            jain=user_context.jain,
            satvik=user_context.satvik,
            disliked_ingredients=list(user_context.disliked_ingredients or []),
        )

    try:
        results_df = recommender.recommend_semantic(
            query=request.query,
            user_preferences=prefs,
            nutrition_goals=goals,
            top_k=request.top_k,
            save_results=False,
            constraint_request=constraint_req,
            user_context=user_context,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Semantic retrieval model artifacts missing: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Semantic retrieval error: {e}",
        )

    items = _format_recommendations_from_df(results_df)
    metrics_collector.record_recommendation("dense_semantic" + ("_personalized" if user_context else ""))

    cand_count = (
        recommender.last_constraint_diagnostics.get("total_candidates", 6871)
        if recommender.last_constraint_diagnostics
        else 6871
    )
    metrics_collector.record_recommendation_event(
        success=True,
        zero_results=len(items) == 0,
        candidates_retrieved=cand_count,
        returned_count=len(items),
    )
    if len(items) > 0:
        metrics_collector.record_impression(len(items))

    query_meta: Dict[str, Any] = {
        "query": request.query,
        "user_preferences": request.user_preferences.model_dump() if request.user_preferences else {},
        "nutrition_goals": request.nutrition_goals.model_dump() if request.nutrition_goals else {},
        "top_k": request.top_k,
        "mode": "dense_semantic",
        "user_id": current_user.id if current_user else None,
        "personalization_applied": user_context is not None,
    }

    if current_user and RECOMMENDATION_HISTORY_ENABLED and recommender.last_ranked_candidates:
        session_id = generate_session_id()
        ranking_method = "xgboost" if getattr(recommender.ranking_dispatcher, "enabled", False) else "hybrid"
        model_version = "xgb_ranker_v0.1.0" if getattr(recommender.ranking_dispatcher, "enabled", False) else "hybrid_v1"
        log_recommendation_events(
            db=db,
            user_id=current_user.id,
            session_id=session_id,
            ranked_candidates=recommender.last_ranked_candidates,
            ranking_method=ranking_method,
            model_version=model_version,
            personalization_applied=True,
            context_metadata=query_meta,
        )

    diagnostics = recommender.last_constraint_diagnostics if constraint_req else None
    message = None
    if len(items) == 0:
        if constraint_req is not None:
            diagnostics = build_zero_result_diagnostics(
                raw_diagnostics=recommender.last_constraint_diagnostics,
                constraint_request=constraint_req,
                total_pool_size=6871,
            )
            message = "No recipes satisfy all specified hard constraints."
        else:
            diagnostics = build_zero_result_diagnostics(
                raw_diagnostics={"total_candidates": 0, "rejected_count": 0},
                constraint_request=None,
                total_pool_size=6871,
            )
            message = "No recipes matched your query criteria."

    return RecommendationResponse(
        query=query_meta,
        count=len(items),
        recommendations=items,
        message=message,
        diagnostics=diagnostics,
    )

