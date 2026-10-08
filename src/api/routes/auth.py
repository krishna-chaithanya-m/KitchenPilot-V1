"""Authentication endpoints for KitchenPilot-V1 API."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.api.config import (
    AUTH_ENABLED,
    ENVIRONMENT,
    GOOGLE_AUTH_ENABLED,
    PILOT_INVITE_CODE,
    PILOT_MAX_USERS,
    PILOT_MODE,
)
from src.api.dependencies import get_db
from src.api.middleware import metrics_collector
from src.personalization.models import UserModel
from src.personalization.schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    MessageResponse,
    PilotStatusResponse,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    UserPreferenceResponse,
    UserProfileResponse,
    UserResponse,
    VerifyEmailRequest,
)
from src.personalization.security import create_access_token
from src.personalization.service import PersonalizationService
from src.services.email import email_service

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
    background_tasks: BackgroundTasks,
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

    # Generate verification token and queue email dispatch in background
    try:
        raw_token = PersonalizationService.create_email_verification_token(db, user.id)
        background_tasks.add_task(email_service.send_verification_email, user.email, raw_token, user.id)
    except Exception as exc:
        logger.warning("Could not queue initial email verification: %s", exc)

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


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify email address with cryptographic token",
)
def verify_email(
    req: VerifyEmailRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Verify user email address using a valid time-bounded verification token."""
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is currently disabled.",
        )

    try:
        PersonalizationService.verify_email_token(db, req.token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return MessageResponse(
        message="Email successfully verified. Your account is now fully active.",
        success=True,
    )


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend email verification message",
)
def resend_verification(
    req: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Resend email verification message to an existing unverified account.

    Anti-enumeration behavior: Always returns success regardless of whether the
    account exists, is already verified, or is unknown.
    """
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is currently disabled.",
        )

    result = PersonalizationService.request_resend_verification(db, req.email)
    if result:
        user, raw_token = result
        background_tasks.add_task(email_service.send_verification_email, user.email, raw_token, user.id)

    return MessageResponse(
        message="If that email address is registered and unverified, verification instructions have been sent.",
        success=True,
    )


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a password recovery email",
)
def forgot_password(
    req: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Initiate password recovery workflow.

    Anti-enumeration behavior: Returns the same successful response whether or not
    the email address is registered, preventing user enumeration attacks.
    """
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is currently disabled.",
        )

    result = PersonalizationService.request_password_reset(db, req.email)
    if result:
        user, raw_token = result
        background_tasks.add_task(email_service.send_password_reset_email, user.email, raw_token, user.id)

    return MessageResponse(
        message="If that email address is registered, instructions to reset your password have been sent.",
        success=True,
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset password using valid recovery token",
)
def reset_password(
    req: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Reset user password using a valid, unexpired, single-use recovery token."""
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is currently disabled.",
        )

    try:
        PersonalizationService.reset_password_with_token(db, req.token, req.new_password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return MessageResponse(
        message="Password successfully reset. You may now log in with your new password.",
        success=True,
    )


@router.post(
    "/google",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate or register user via Google OAuth/OIDC ID token",
)
def auth_google(
    req: GoogleAuthRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Authenticate or register user using a cryptographically verified Google ID token."""
    from src.api.config import AUTH_ENABLED, GOOGLE_AUTH_ENABLED

    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is currently disabled.",
        )

    if not GOOGLE_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication is currently disabled.",
        )

    try:
        user, is_new = PersonalizationService.authenticate_google_user(
            db=db,
            id_token_str=req.id_token,
            invite_code=req.invite_code,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except ValueError as exc:
        err_msg = str(exc)
        if "conflict" in err_msg.lower() or "already linked" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=err_msg,
            )
        # Log error without exposing raw token
        logger.warning("Google authentication failed: %s", err_msg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err_msg if "Google" in err_msg else "Google authentication failed.",
        )

    if is_new:
        metrics_collector.record_registration()
    else:
        metrics_collector.record_login()

    token, expires_in = create_access_token(subject=user.id)
    user_resp = UserResponse.model_validate(user)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=user_resp,
    )
