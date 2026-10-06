"""KitchenPilot Relational Database Layer."""

from src.db.base import Base
from src.db.config import DATA_BACKEND, get_database_url, is_postgres_backend
from src.db.models import (
    DatasetManifestMetadataModel,
    IngredientAliasModel,
    IngredientModel,
    RecipeIngredientModel,
    RecipeIngredientNutritionModel,
    RecipeModel,
    RecipeNutritionModel,
)
from src.db.session import (
    check_db_connection,
    get_db_session,
    get_engine,
    get_session_factory,
)

__all__ = [
    "Base",
    "DATA_BACKEND",
    "get_database_url",
    "is_postgres_backend",
    "RecipeModel",
    "IngredientModel",
    "IngredientAliasModel",
    "RecipeIngredientModel",
    "RecipeNutritionModel",
    "RecipeIngredientNutritionModel",
    "DatasetManifestMetadataModel",
    "get_engine",
    "get_session_factory",
    "get_db_session",
    "check_db_connection",
]
