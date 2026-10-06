"""KitchenPilot-V1 Personalization & User Feedback Module."""

from src.personalization.features import (
    PERSONALIZATION_FEATURE_SCHEMA_VERSION,
    PersonalizationSignals,
    UserPersonalizationContext,
    extract_personalization_signals,
)
from src.personalization.history import generate_session_id, log_recommendation_events
from src.personalization.models import (
    RecommendationHistoryModel,
    UserFeedbackModel,
    UserModel,
    UserNutritionTargetModel,
    UserPantryModel,
    UserPreferenceModel,
)
from src.personalization.schemas import (
    AuthResponse,
    FeedbackRequest,
    FeedbackResponse,
    FeedbackType,
    LoginRequest,
    NutritionTargetRequest,
    NutritionTargetResponse,
    PantryItemCreateRequest,
    PantryItemResponse,
    PantryStatus,
    RecommendationHistoryItem,
    RecommendationHistoryResponse,
    RegisterRequest,
    UpdatePreferencesRequest,
    UserPreferenceResponse,
    UserProfileResponse,
    UserResponse,
)
from src.personalization.scorer import PersonalizationScorer
from src.personalization.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from src.personalization.service import PersonalizationService

__all__ = [
    "PERSONALIZATION_FEATURE_SCHEMA_VERSION",
    "PersonalizationSignals",
    "UserPersonalizationContext",
    "extract_personalization_signals",
    "generate_session_id",
    "log_recommendation_events",
    "UserModel",
    "UserPreferenceModel",
    "UserNutritionTargetModel",
    "UserPantryModel",
    "UserFeedbackModel",
    "RecommendationHistoryModel",
    "FeedbackType",
    "PantryStatus",
    "RegisterRequest",
    "LoginRequest",
    "UserResponse",
    "AuthResponse",
    "UserPreferenceResponse",
    "UpdatePreferencesRequest",
    "NutritionTargetResponse",
    "NutritionTargetRequest",
    "UserProfileResponse",
    "PantryItemCreateRequest",
    "PantryItemResponse",
    "FeedbackRequest",
    "FeedbackResponse",
    "RecommendationHistoryItem",
    "RecommendationHistoryResponse",
    "PersonalizationScorer",
    "PersonalizationService",
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
]
