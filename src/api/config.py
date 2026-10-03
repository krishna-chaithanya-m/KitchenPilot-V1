"""API Configuration for KitchenPilot-V1.

Loads environment variables with robust local-development defaults and
resolves project paths relative to the project root.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

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
