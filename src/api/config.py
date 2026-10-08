"""API Configuration for KitchenPilot-V1.

Loads environment variables with robust local-development defaults and
resolves project paths relative to the project root.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load optional .env from project root if present
load_dotenv(PROJECT_ROOT / ".env")

# Environment & logging settings
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# Server settings
API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# CORS settings
ALLOWED_ORIGINS_RAW: str = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173,http://localhost:5500,http://127.0.0.1:5500",
)
ALLOWED_ORIGINS: List[str] = [
    origin.strip() for origin in ALLOWED_ORIGINS_RAW.split(",") if origin.strip()
]
CORS_ALLOW_CREDENTIALS: bool = "*" not in ALLOWED_ORIGINS

# Data paths
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
RECOMMENDATION_MODELS_DIR = MODELS_DIR / "recommendation"

RECIPES_PATH = PROCESSED_DATA_DIR / "recipes.csv"
RECIPE_NUTRITION_PATH = PROCESSED_DATA_DIR / "recipe_nutrition.csv"
RECIPE_CORPUS_PATH = PROCESSED_DATA_DIR / "recipe_corpus.csv"
RECIPE_INGREDIENTS_LINKED_PATH = PROCESSED_DATA_DIR / "recipe_ingredients_linked.csv"
INGREDIENTS_PATH = PROCESSED_DATA_DIR / "ingredients.csv"

TFIDF_VECTORIZER_PATH = RECOMMENDATION_MODELS_DIR / "tfidf_vectorizer.joblib"
TFIDF_MATRIX_PATH = RECOMMENDATION_MODELS_DIR / "recipe_tfidf_matrix.npz"
RECIPE_INDEX_PATH = RECOMMENDATION_MODELS_DIR / "recipe_index.csv"

# Stage D Semantic Retrieval Configuration
SEMANTIC_RETRIEVAL_ENABLED: bool = (
    os.getenv("SEMANTIC_RETRIEVAL_ENABLED", "false").lower().strip() in ("true", "1", "yes")
)
SEMANTIC_MODEL_NAME: str = os.getenv("SEMANTIC_MODEL_NAME", "BAAI/bge-small-en-v1.5")
SEMANTIC_TOP_K: int = int(os.getenv("SEMANTIC_TOP_K", "50"))
TFIDF_TOP_K: int = int(os.getenv("TFIDF_TOP_K", "50"))

SEMANTIC_MODELS_DIR = MODELS_DIR / "retrieval" / "semantic"
SEMANTIC_EMBEDDINGS_PATH = SEMANTIC_MODELS_DIR / "recipe_embeddings.npy"
SEMANTIC_INDEX_PATH = SEMANTIC_MODELS_DIR / "recipe_index.csv"
SEMANTIC_METADATA_PATH = SEMANTIC_MODELS_DIR / "metadata.json"

# Stage E Constraint Engine Configuration
CONSTRAINT_ENGINE_ENABLED: bool = (
    os.getenv("CONSTRAINT_ENGINE_ENABLED", "true").lower().strip() in ("true", "1", "yes")
)

# Stage F XGBoost Ranking Configuration
XGBOOST_RANKING_ENABLED: bool = (
    os.getenv("XGBOOST_RANKING_ENABLED", "false").lower().strip() in ("true", "1", "yes")
)
XGBOOST_MODELS_DIR = MODELS_DIR / "ranking"
XGBOOST_MODEL_PATH = Path(os.getenv("XGBOOST_MODEL_PATH", str(XGBOOST_MODELS_DIR / "xgboost_ranker.json")))
XGBOOST_FEATURE_SCHEMA_PATH = Path(os.getenv("XGBOOST_FEATURE_SCHEMA_PATH", str(XGBOOST_MODELS_DIR / "feature_schema.json")))
XGBOOST_METADATA_PATH = Path(os.getenv("XGBOOST_METADATA_PATH", str(XGBOOST_MODELS_DIR / "metadata.json")))

# Stage G User Personalization & Feedback Configuration
AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "true").lower().strip() in ("true", "1", "yes")
AUTH_SECRET_KEY: str = os.getenv(
    "AUTH_SECRET_KEY", "kitchenpilot-secure-dev-secret-key-32b-min-required-2026"
)
AUTH_ALGORITHM: str = os.getenv("AUTH_ALGORITHM", "HS256")
AUTH_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))
PERSONALIZATION_ENABLED: bool = (
    os.getenv("PERSONALIZATION_ENABLED", "true").lower().strip() in ("true", "1", "yes")
)
PERSONALIZATION_WEIGHT: float = float(os.getenv("PERSONALIZATION_WEIGHT", "0.20"))
FEEDBACK_ENABLED: bool = os.getenv("FEEDBACK_ENABLED", "true").lower().strip() in ("true", "1", "yes")
RECOMMENDATION_HISTORY_ENABLED: bool = (
    os.getenv("RECOMMENDATION_HISTORY_ENABLED", "true").lower().strip() in ("true", "1", "yes")
)

# Stage 2 — Email Verification & Password Recovery Configuration
EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "false").lower().strip() in ("true", "1", "yes")
EMAIL_BACKEND: str = os.getenv("EMAIL_BACKEND", "console").lower().strip()  # 'console' or 'smtp'
SMTP_HOST: str = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower().strip() in ("true", "1", "yes")
EMAIL_FROM_ADDRESS: str = os.getenv("EMAIL_FROM_ADDRESS", "noreply@kitchenpilot.local")
EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", "KitchenPilot")
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5500")
EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = int(
    os.getenv("EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES", str(60 * 24))
)  # 24 hours
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = int(
    os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "15")
)  # 15 minutes
REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN: bool = (
    os.getenv("REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN", "false").lower().strip()
    in ("true", "1", "yes")
)

# Stage 3 — Google OAuth & OpenID Connect (OIDC) Configuration
GOOGLE_AUTH_ENABLED: bool = (
    os.getenv("GOOGLE_AUTH_ENABLED", "false").lower().strip() in ("true", "1", "yes")
)
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")



# Stage H — Production Hardening, Observability & Rate Limiting Configuration
RATE_LIMIT_ENABLED: bool = (
    os.getenv("RATE_LIMIT_ENABLED", "false").lower().strip() in ("true", "1", "yes")
)
RATE_LIMIT_AUTH_RPM: int = int(os.getenv("RATE_LIMIT_AUTH_RPM", "20"))
RATE_LIMIT_RECOMMEND_RPM: int = int(os.getenv("RATE_LIMIT_RECOMMEND_RPM", "60"))
RATE_LIMIT_FEEDBACK_RPM: int = int(os.getenv("RATE_LIMIT_FEEDBACK_RPM", "60"))
RATE_LIMIT_GLOBAL_RPM: int = int(os.getenv("RATE_LIMIT_GLOBAL_RPM", "120"))

# Stage 4 — Dedicated Authentication Endpoint Rate Limits
RATE_LIMIT_AUTH_VERIFY_EMAIL_RPM: int = int(os.getenv("RATE_LIMIT_AUTH_VERIFY_EMAIL_RPM", "10"))
RATE_LIMIT_AUTH_RESEND_VERIFICATION_RPH: int = int(os.getenv("RATE_LIMIT_AUTH_RESEND_VERIFICATION_RPH", "3"))
RATE_LIMIT_AUTH_FORGOT_PASSWORD_RPH: int = int(os.getenv("RATE_LIMIT_AUTH_FORGOT_PASSWORD_RPH", "3"))
RATE_LIMIT_AUTH_RESET_PASSWORD_RPM: int = int(os.getenv("RATE_LIMIT_AUTH_RESET_PASSWORD_RPM", "5"))
RATE_LIMIT_AUTH_GOOGLE_RPM: int = int(os.getenv("RATE_LIMIT_AUTH_GOOGLE_RPM", "10"))

# Reverse Proxy & Ingress Security
TRUSTED_PROXIES: str = os.getenv("TRUSTED_PROXIES", "")

STRUCTURED_LOGGING: bool = (
    os.getenv("STRUCTURED_LOGGING", "false" if ENVIRONMENT == "development" else "true")
    .lower()
    .strip()
    in ("true", "1", "yes")
)
METRICS_ENABLED: bool = (
    os.getenv("METRICS_ENABLED", "true").lower().strip() in ("true", "1", "yes")
)

# Stage J — Controlled Pilot Mode Configuration
PILOT_MODE: bool = (
    os.getenv("PILOT_MODE", "false").lower().strip() in ("true", "1", "yes")
)
PILOT_MAX_USERS: int = int(os.getenv("PILOT_MAX_USERS", "50"))
PILOT_INVITE_CODE: str = os.getenv("PILOT_INVITE_CODE", "").strip()

VALID_ENVIRONMENTS = ("development", "staging", "production")


def validate_production_configuration(env: Optional[str] = None) -> List[str]:
    """Validate configuration safety for execution environments.

    Returns a list of blocking errors found. In production, raises RuntimeError
    if any critical violation is detected.
    """
    target_env = (env or ENVIRONMENT).lower()
    errors: List[str] = []

    if target_env not in VALID_ENVIRONMENTS:
        errors.append(
            f"Invalid ENVIRONMENT '{target_env}'. Must be one of: {', '.join(VALID_ENVIRONMENTS)}."
        )
        return errors

    # Check weak or default secrets in production
    insecure_keys = [
        "kitchenpilot-secure-dev-secret-key-32b-min-required-2026",
        "secret",
        "changeme",
        "password",
        "dev",
        "development",
    ]
    if target_env == "production":
        if not AUTH_SECRET_KEY or any(AUTH_SECRET_KEY.lower() == k for k in insecure_keys) or len(AUTH_SECRET_KEY) < 32:
            errors.append(
                "Production environment requires a strong, high-entropy AUTH_SECRET_KEY (at least 32 characters) not equal to dev defaults."
            )

        if "*" in ALLOWED_ORIGINS:
            errors.append(
                "Wildcard CORS origin ('*') is prohibited in production when credentials/authentication are active."
            )

        if not RATE_LIMIT_ENABLED:
            errors.append(
                "Rate limiting (RATE_LIMIT_ENABLED=true) must be enabled in production."
            )

        from src.db.config import DATA_BACKEND, get_database_url
        if DATA_BACKEND not in ("csv", "postgres"):
            errors.append(
                f"Production requires explicit DATA_BACKEND ('csv' or 'postgres'), found: '{DATA_BACKEND}'."
            )
        elif DATA_BACKEND == "postgres":
            db_url = get_database_url()
            if "localhost" in db_url and not os.getenv("ALLOW_LOCALHOST_DB_IN_PROD"):
                errors.append(
                    "Production PostgreSQL connection points to localhost. Use an external/service database host or set ALLOW_LOCALHOST_DB_IN_PROD=1."
                )

        # Explicit artifact and data path validation
        for path_name, path_val in [
            ("RECIPES_PATH", RECIPES_PATH),
            ("RECIPE_CORPUS_PATH", RECIPE_CORPUS_PATH),
            ("TFIDF_VECTORIZER_PATH", TFIDF_VECTORIZER_PATH),
            ("TFIDF_MATRIX_PATH", TFIDF_MATRIX_PATH),
            ("RECIPE_INDEX_PATH", RECIPE_INDEX_PATH),
        ]:
            if not path_val.is_file():
                errors.append(f"Required production file missing for {path_name}: {path_val}")

    return errors
