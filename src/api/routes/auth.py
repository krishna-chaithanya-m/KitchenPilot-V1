"""Authentication endpoints for KitchenPilot-V1 API."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from sqlalchemy import func
from src.api.config import (
    AUTH_ENABLED,
    ENVIRONMENT,
    PILOT_INVITE_CODE,
    PILOT_MAX_USERS,
    PILOT_MODE,
)
from src.api.dependencies import get_db
from src.api.middleware import metrics_collector
from src.personalization.models import UserModel
from src.personalization.schemas import (
    AuthResponse,
    LoginRequest,
    PilotStatusResponse,
    RegisterRequest,
    UserPreferenceResponse,
    UserProfileResponse,
    UserResponse,
)
from src.personalization.security import create_access_token
from src.personalization.service import PersonalizationService

logger = logging.getLogger("kitchenpilot.api.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.get(
    "/pilot-status",
    response_model=PilotStatusResponse,
    summary="Get controlled pilot cohort status and capacity",
)
def get_pilot_status(
    db: Session = Depends(get_db),
) -> PilotStatusResponse:
    """Retrieve public pilot cohort capacity and active enrollment without exposing secrets."""
    user_count = db.query(func.count(UserModel.id)).scalar() or 0
    available = max(0, PILOT_MAX_USERS - user_count)
    return PilotStatusResponse(
        pilot_mode=PILOT_MODE,
        active_participants=user_count,
        capacity=PILOT_MAX_USERS,
        available_slots=available,
        invite_code_required=bool(PILOT_INVITE_CODE),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(
    req: RegisterRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Register a new user with email, password, and optional display name."""
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is currently disabled.",
        )

    # In production, explicit pilot activation is required (Kill switch / Pause)
    if ENVIRONMENT == "production" and not PILOT_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pilot onboarding is currently paused. Please check back later.",
        )

    if PILOT_MODE:
        user_count = db.query(func.count(UserModel.id)).scalar() or 0
        if user_count >= PILOT_MAX_USERS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Controlled pilot cohort capacity reached ({PILOT_MAX_USERS} max users).",
            )
        if PILOT_INVITE_CODE:
            if not req.invite_code or req.invite_code.strip() != PILOT_INVITE_CODE:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid or missing pilot invite code.",
                )

    try:
        user = PersonalizationService.register_user(db, req)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    metrics_collector.record_registration()
    token, expires_in = create_access_token(subject=user.id)
    user_resp = UserResponse.model_validate(user)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=user_resp,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and obtain JWT access token",
)
def login(
    req: LoginRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Authenticate with registered email and password to receive a JWT access token."""
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is currently disabled.",
        )

    user = PersonalizationService.authenticate_user(db, req)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    metrics_collector.record_login(user.id)
    token, expires_in = create_access_token(subject=user.id)
    user_resp = UserResponse.model_validate(user)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=user_resp,
    )
