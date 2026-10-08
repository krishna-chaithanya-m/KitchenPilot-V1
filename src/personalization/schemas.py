"""Pydantic v2 schemas for authentication, user profiles, pantry, feedback, and history."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FeedbackType(str, Enum):
    """Supported recipe interaction feedback types."""
    IMPRESSION = "IMPRESSION"
    LIKE = "LIKE"
    DISLIKE = "DISLIKE"
    SAVE = "SAVE"
    COOKED = "COOKED"
    HIDE = "HIDE"


class PantryStatus(str, Enum):
    """Pantry inventory availability status."""
    IN_STOCK = "IN_STOCK"
    LOW = "LOW"
    OUT_OF_STOCK = "OUT_OF_STOCK"


# --- Auth Schemas ---

class RegisterRequest(BaseModel):
    """User account registration payload."""
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="Secure user password (min 8 characters)")
    display_name: Optional[str] = Field(None, max_length=128, description="Optional public display name")
    invite_code: Optional[str] = Field(None, max_length=64, description="Optional pilot invite code")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        clean = v.strip().lower()
        email_regex = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        if not re.match(email_regex, clean):
            raise ValueError("Invalid email address format.")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter.")
        if not re.search(r"[0-9!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one digit or special character.")
        return v


class LoginRequest(BaseModel):
    """User login credential payload."""
    email: str = Field(..., description="Registered email address")
    password: str = Field(..., description="User password")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    """Public user identity schema."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: Optional[str] = None
    is_active: bool
    is_verified: bool = False
    auth_provider: str = "local"
    created_at: datetime
    last_login_at: Optional[datetime] = None


class AuthResponse(BaseModel):
    """Authentication token response payload."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    """Standard message response schema for operations."""
    message: str
    success: bool = True


class VerifyEmailRequest(BaseModel):
    """Email verification payload."""
    token: str = Field(..., min_length=16, max_length=256, description="Cryptographic verification token")


class ResendVerificationRequest(BaseModel):
    """Resend email verification payload."""
    email: str = Field(..., description="Registered account email address")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        clean = v.strip().lower()
        email_regex = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        if not re.match(email_regex, clean):
            raise ValueError("Invalid email address format.")
        return clean


class ForgotPasswordRequest(BaseModel):
    """Forgot password request payload."""
    email: str = Field(..., description="Registered account email address")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        clean = v.strip().lower()
        email_regex = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        if not re.match(email_regex, clean):
            raise ValueError("Invalid email address format.")
        return clean


class ResetPasswordRequest(BaseModel):
    """Password reset payload with new password."""
    token: str = Field(..., min_length=16, max_length=256, description="Cryptographic password reset token")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New secure password (min 8 characters)",
    )

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter.")
        if not re.search(r"[0-9!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one digit or special character.")
        return v


class GoogleAuthRequest(BaseModel):
    """Google OAuth/OIDC authentication payload."""
    id_token: str = Field(..., min_length=10, description="Cryptographic Google OIDC ID token")
    invite_code: Optional[str] = Field(None, max_length=64, description="Optional pilot invite code")



# --- Preference Schemas ---

class UserPreferenceResponse(BaseModel):
    """User preference response schema."""
    model_config = ConfigDict(from_attributes=True)

    vegetarian: bool = False
    vegan: bool = False
    jain: bool = False
    satvik: bool = False
    preferred_cuisines: List[str] = Field(default_factory=list)
    preferred_regions: List[str] = Field(default_factory=list)
    preferred_meal_types: List[str] = Field(default_factory=list)
    preferred_categories: List[str] = Field(default_factory=list)
    preferred_ingredients: List[str] = Field(default_factory=list)
    disliked_ingredients: List[str] = Field(default_factory=list)


class UpdatePreferencesRequest(BaseModel):
    """User preference update payload."""
    vegetarian: Optional[bool] = None
    vegan: Optional[bool] = None
    jain: Optional[bool] = None
    satvik: Optional[bool] = None
    preferred_cuisines: Optional[List[str]] = None
    preferred_regions: Optional[List[str]] = None
    preferred_meal_types: Optional[List[str]] = None
    preferred_categories: Optional[List[str]] = None
    preferred_ingredients: Optional[List[str]] = None
    disliked_ingredients: Optional[List[str]] = None

    # Singular aliases for frontend form compatibility
    cuisine: Optional[str] = None
    region: Optional[str] = None
    meal_type: Optional[str] = None
    category: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_singular_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("cuisine") and not data.get("preferred_cuisines"):
                c = data["cuisine"]
                if isinstance(c, str):
                    data["preferred_cuisines"] = [x.strip() for x in c.split(",") if x.strip()]
                elif isinstance(c, list):
                    data["preferred_cuisines"] = c
            if data.get("region") and not data.get("preferred_regions"):
                r = data["region"]
                if isinstance(r, str):
                    data["preferred_regions"] = [x.strip() for x in r.split(",") if x.strip()]
                elif isinstance(r, list):
                    data["preferred_regions"] = r
            if data.get("meal_type") and not data.get("preferred_meal_types"):
                m = data["meal_type"]
                if isinstance(m, str):
                    data["preferred_meal_types"] = [x.strip() for x in m.split(",") if x.strip()]
                elif isinstance(m, list):
                    data["preferred_meal_types"] = m
            if data.get("category") and not data.get("preferred_categories"):
                cat = data["category"]
                if isinstance(cat, str):
                    data["preferred_categories"] = [x.strip() for x in cat.split(",") if x.strip()]
                elif isinstance(cat, list):
                    data["preferred_categories"] = cat
        return data


# --- Nutrition Target Schemas ---

class NutritionTargetResponse(BaseModel):
    """User nutrition targets response schema."""
    model_config = ConfigDict(from_attributes=True)

    target_calories: Optional[float] = None
    min_calories: Optional[float] = None
    max_calories: Optional[float] = None
    target_protein: Optional[float] = None
    min_protein: Optional[float] = None
    max_protein: Optional[float] = None
    target_carbs: Optional[float] = None
    min_carbs: Optional[float] = None
    max_carbs: Optional[float] = None
    target_fat: Optional[float] = None
    min_fat: Optional[float] = None
    max_fat: Optional[float] = None
    target_fiber: Optional[float] = None
    min_fiber: Optional[float] = None
    max_fiber: Optional[float] = None


class NutritionTargetRequest(BaseModel):
    """User nutrition targets update payload."""
    target_calories: Optional[float] = Field(None, ge=0, le=5000)
    min_calories: Optional[float] = Field(None, ge=0, le=5000)
    max_calories: Optional[float] = Field(None, ge=0, le=5000)
    target_protein: Optional[float] = Field(None, ge=0, le=500)
    min_protein: Optional[float] = Field(None, ge=0, le=500)
    max_protein: Optional[float] = Field(None, ge=0, le=500)
    target_carbs: Optional[float] = Field(None, ge=0, le=500)
    min_carbs: Optional[float] = Field(None, ge=0, le=500)
    max_carbs: Optional[float] = Field(None, ge=0, le=500)
    target_fat: Optional[float] = Field(None, ge=0, le=500)
    min_fat: Optional[float] = Field(None, ge=0, le=500)
    max_fat: Optional[float] = Field(None, ge=0, le=500)
    target_fiber: Optional[float] = Field(None, ge=0, le=200)
    min_fiber: Optional[float] = Field(None, ge=0, le=200)
    max_fiber: Optional[float] = Field(None, ge=0, le=200)

    @field_validator("max_calories")
    @classmethod
    def validate_calories_bounds(cls, v: Optional[float], info) -> Optional[float]:
        min_cal = info.data.get("min_calories")
        if v is not None and min_cal is not None and v < min_cal:
            raise ValueError("max_calories cannot be less than min_calories.")
        return v

    @field_validator("max_protein")
    @classmethod
    def validate_protein_bounds(cls, v: Optional[float], info) -> Optional[float]:
        min_p = info.data.get("min_protein")
        if v is not None and min_p is not None and v < min_p:
            raise ValueError("max_protein cannot be less than min_protein.")
        return v


class UserProfileResponse(BaseModel):
    """Full user profile aggregation."""
    user: UserResponse
    preferences: Optional[UserPreferenceResponse] = None
    nutrition_targets: Optional[NutritionTargetResponse] = None
    pantry_item_count: int = 0


# --- Pantry Schemas ---

class PantryItemCreateRequest(BaseModel):
    """Payload to add or update an ingredient in the user pantry."""
    ingredient_name: str = Field(..., min_length=1, max_length=256)
    quantity: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=64)
    status: PantryStatus = PantryStatus.IN_STOCK

    @field_validator("ingredient_name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().upper()
            try:
                return PantryStatus(clean)
            except ValueError:
                return v
        return v


class PantryItemResponse(BaseModel):
    """User pantry item response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ingredient_id: Optional[str] = None
    ingredient_name: str
    display_name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    status: PantryStatus
    updated_at: datetime


# --- Feedback Schemas ---

class FeedbackRequest(BaseModel):
    """User recipe interaction feedback submission."""
    recipe_id: str = Field(..., min_length=1, max_length=16)
    feedback_type: FeedbackType
    rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    notes: Optional[str] = Field(None, max_length=1000)
    session_id: Optional[str] = Field(None, max_length=64, description="Optional recommendation session ID")


class FeedbackResponse(BaseModel):
    """User recipe feedback response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipe_id: str
    recipe_name: Optional[str] = None
    feedback_type: FeedbackType
    rating: Optional[float] = None
    notes: Optional[str] = None
    session_id: Optional[str] = None
    created_at: datetime


# --- History Schemas ---

class RecommendationHistoryItem(BaseModel):
    """Single recommendation event entry."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    recipe_id: str
    recipe_name: Optional[str] = None
    position: int
    ranking_method: str
    model_version: str
    personalization_applied: bool
    base_score: float
    personalization_score: float
    final_score: float
    created_at: datetime


class RecommendationHistoryResponse(BaseModel):
    """Paginated recommendation event history response."""
    total_events: int
    items: List[RecommendationHistoryItem]


# --- Pilot Operations Schemas (Stage K) ---

class PilotStatusResponse(BaseModel):
    """Controlled pilot cohort status and capacity overview."""
    pilot_mode: bool
    active_participants: int
    capacity: int
    available_slots: int
    invite_code_required: bool


class PilotParticipantResponse(BaseModel):
    """Pilot participant status information."""
    user_id: int
    email: str
    display_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    feedback_count: int
    history_count: int


# --- Qualitative Pilot UX Feedback Schemas (Stage L) ---

class QualitativeIssueType(str, Enum):
    """Issue types for lightweight qualitative pilot feedback (kept separate from ML labels)."""
    RECOMMENDATION_IRRELEVANT = "recommendation_irrelevant"
    MISSING_INGREDIENT = "missing_ingredient"
    WRONG_DIETARY_MATCH = "wrong_dietary_match"
    NUTRITION_INFORMATION_ISSUE = "nutrition_information_issue"
    POOR_EXPLANATION = "poor_explanation"
    SLOW_RESPONSE = "slow_response"
    CONFUSING_UI = "confusing_ui"
    USEFUL_RECOMMENDATION = "useful_recommendation"
    OTHER_ISSUE = "other_issue"


class QualitativeFeedbackRequest(BaseModel):
    """Payload to submit lightweight qualitative user feedback."""
    recipe_id: Optional[str] = Field(None, max_length=16, description="Optional target recipe ID")
    session_id: Optional[str] = Field(None, max_length=64, description="Optional recommendation session ID")
    issue_type: QualitativeIssueType = Field(..., description="Categorical classification of the qualitative feedback")
    comments: Optional[str] = Field(None, max_length=2000, description="Optional open-ended text commentary")


class QualitativeFeedbackResponse(BaseModel):
    """Response payload for recorded qualitative feedback."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    recipe_id: Optional[str] = None
    session_id: Optional[str] = None
    issue_type: QualitativeIssueType
    comments: Optional[str] = None
    created_at: datetime

