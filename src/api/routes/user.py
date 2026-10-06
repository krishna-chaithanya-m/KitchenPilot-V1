"""User profile, preferences, pantry, feedback, and history endpoints."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db
from src.personalization.models import UserModel
from src.personalization.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    FeedbackType,
    NutritionTargetRequest,
    NutritionTargetResponse,
    PantryItemCreateRequest,
    PantryItemResponse,
    PilotParticipantResponse,
    QualitativeFeedbackRequest,
    QualitativeFeedbackResponse,
    RecommendationHistoryItem,
    RecommendationHistoryResponse,
    UpdatePreferencesRequest,
    UserPreferenceResponse,
    UserProfileResponse,
    UserResponse,
)
from src.personalization.service import PersonalizationService

logger = logging.getLogger("kitchenpilot.api.user")

router = APIRouter(prefix="/api/v1/user", tags=["User & Personalization"])


@router.get(
    "/profile",
    response_model=UserProfileResponse,
    summary="Get authenticated user profile, preferences, and nutrition targets",
)
def get_profile(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileResponse:
    """Retrieve the full profile for the authenticated user."""
    prefs = PersonalizationService.get_user_preferences(db, current_user.id)
    targets = PersonalizationService.get_user_nutrition_targets(db, current_user.id)
    pantry = PersonalizationService.get_user_pantry(db, current_user.id)

    user_resp = UserResponse.model_validate(current_user)
    prefs_resp = UserPreferenceResponse.model_validate(prefs) if prefs else None
    targets_resp = NutritionTargetResponse.model_validate(targets) if targets else None

    return UserProfileResponse(
        user=user_resp,
        preferences=prefs_resp,
        nutrition_targets=targets_resp,
        pantry_item_count=len(pantry),
    )


@router.put(
    "/preferences",
    response_model=UserPreferenceResponse,
    summary="Update user dietary and cuisine preferences",
)
def update_preferences(
    req: UpdatePreferencesRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferenceResponse:
    """Update dietary restrictions, preferred cuisines, regions, meal types, and ingredient affinities."""
    updated = PersonalizationService.update_user_preferences(db, current_user.id, req)
    return UserPreferenceResponse.model_validate(updated)


@router.put(
    "/nutrition-targets",
    response_model=NutritionTargetResponse,
    summary="Update user daily or per-meal nutrition targets",
)
def update_nutrition_targets(
    req: NutritionTargetRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NutritionTargetResponse:
    """Update target calorie, protein, carbohydrate, fat, and fiber limits."""
    updated = PersonalizationService.update_user_nutrition_targets(db, current_user.id, req)
    return NutritionTargetResponse.model_validate(updated)


@router.get(
    "/pantry",
    response_model=List[PantryItemResponse],
    summary="List all items in the user pantry",
)
def get_pantry(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[PantryItemResponse]:
    """Retrieve the persistent pantry inventory for the authenticated user."""
    items = PersonalizationService.get_user_pantry(db, current_user.id)
    return [PantryItemResponse.model_validate(i) for i in items]


@router.post(
    "/pantry",
    response_model=PantryItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or update an ingredient in the user pantry",
)
def add_pantry_item(
    req: PantryItemCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PantryItemResponse:
    """Add a new ingredient or update inventory status in the authenticated user's pantry."""
    item = PersonalizationService.add_or_update_pantry_item(db, current_user.id, req)
    return PantryItemResponse.model_validate(item)


@router.delete(
    "/pantry/{item_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove an ingredient from the user pantry",
)
def delete_pantry_item(
    item_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Remove a pantry item owned by the authenticated user."""
    success = PersonalizationService.remove_pantry_item(db, current_user.id, item_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pantry item with id {item_id} not found.",
        )
    return {"status": "deleted", "id": item_id}


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit explicit recipe interaction feedback",
)
def record_feedback(
    req: FeedbackRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    """Submit explicit feedback (LIKE, DISLIKE, SAVE, COOKED, HIDE) for a recipe."""
    fb = PersonalizationService.record_feedback(db, current_user.id, req)
    try:
        from src.api.middleware import metrics_collector
        metrics_collector.record_feedback(req.feedback_type.value)
    except Exception:
        pass
    return FeedbackResponse.model_validate(fb)


@router.get(
    "/feedback",
    response_model=List[FeedbackResponse],
    summary="Retrieve user recipe interaction feedback",
)
def get_feedback(
    feedback_type: Optional[FeedbackType] = None,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[FeedbackResponse]:
    """Retrieve explicit recipe feedback submitted by the authenticated user."""
    type_str = feedback_type.value if feedback_type else None
    items = PersonalizationService.get_user_feedback(db, current_user.id, feedback_type=type_str)
    return [FeedbackResponse.model_validate(i) for i in items]


@router.post(
    "/qualitative-feedback",
    response_model=QualitativeFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit lightweight qualitative UX or recommendation issue feedback",
)
def submit_qualitative_feedback(
    req: QualitativeFeedbackRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QualitativeFeedbackResponse:
    """Submit lightweight qualitative feedback on UX, explanations, dietary accuracy, or relevance.

    Note: In accordance with Stage L rules, qualitative feedback is kept strictly separate
    from structured ML training interactions.
    """
    item = PersonalizationService.record_qualitative_feedback(db, current_user.id, req)
    return QualitativeFeedbackResponse.model_validate(item)


@router.get(
    "/qualitative-feedback",
    response_model=List[QualitativeFeedbackResponse],
    summary="Retrieve qualitative feedback submitted by authenticated user",
)
def get_user_qualitative_feedback(
    recipe_id: Optional[str] = Query(None, description="Filter by recipe ID"),
    issue_type: Optional[str] = Query(None, description="Filter by issue type"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[QualitativeFeedbackResponse]:
    """Retrieve qualitative feedback items submitted by the authenticated user."""
    items = PersonalizationService.get_qualitative_feedback(
        db=db,
        user_id=current_user.id,
        recipe_id=recipe_id,
        issue_type=issue_type,
    )
    return [QualitativeFeedbackResponse.model_validate(i) for i in items]


@router.get(
    "/history",
    response_model=RecommendationHistoryResponse,
    summary="Retrieve recommendation audit history",
)
def get_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationHistoryResponse:
    """Retrieve paginated recommendation events recorded for the authenticated user."""
    total, items = PersonalizationService.get_user_history(db, current_user.id, limit=limit, offset=offset)
    history_items = [RecommendationHistoryItem.model_validate(i) for i in items]
    return RecommendationHistoryResponse(
        total_events=total,
        items=history_items,
    )


@router.delete(
    "/data",
    status_code=status.HTTP_200_OK,
    summary="Purge authenticated user data and preferences",
)
def purge_user_data(
    delete_account: bool = Query(False, description="Whether to also permanently delete the user account"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Securely purge all user-owned data (pantry, feedback, history, preferences, nutrition targets).

    In accordance with privacy and safety invariants:
    - Only the authenticated user's own data is deleted.
    - Shared recipe catalog and ingredient ontology are never modified.
    """
    return PersonalizationService.delete_user_data(
        db=db,
        user_id=current_user.id,
        delete_account=delete_account,
    )


@router.get(
    "/pilot-status",
    response_model=PilotParticipantResponse,
    summary="Get authenticated pilot participant status and activity metrics",
)
def get_user_pilot_status(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PilotParticipantResponse:
    """Retrieve participant enrollment and engagement metadata."""
    from sqlalchemy import func
    from src.personalization.models import RecommendationHistoryModel, UserFeedbackModel

    fb_count = db.query(func.count(UserFeedbackModel.id)).where(UserFeedbackModel.user_id == current_user.id).scalar() or 0
    hist_count = db.query(func.count(RecommendationHistoryModel.id)).where(RecommendationHistoryModel.user_id == current_user.id).scalar() or 0

    return PilotParticipantResponse(
        user_id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
        feedback_count=fb_count,
        history_count=hist_count,
    )


@router.post(
    "/deactivate",
    status_code=status.HTTP_200_OK,
    summary="Deactivate authenticated pilot participant account",
)
def deactivate_account(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Deactivate user account, preventing further authentication and pilot activity."""
    current_user.is_active = False
    db.commit()
    return {"status": "deactivated", "user_id": current_user.id}
