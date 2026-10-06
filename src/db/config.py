"""Database configuration and environment settings for KitchenPilot."""

from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

# Backend selection: 'csv' (default) or 'postgres'
DATA_BACKEND: str = os.getenv("DATA_BACKEND", "csv").lower().strip()

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/kitchenpilot"


def get_database_url() -> str:
    """Retrieve normalized database connection URL.
    
    Ensures that standard 'postgresql://' URLs are translated to use
    the modern psycopg v3 driver 'postgresql+psycopg://'.
    """
    raw_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+psycopg://", 1)
    return raw_url


def is_postgres_backend() -> bool:
    """Check if the active data backend is configured as PostgreSQL."""
    return DATA_BACKEND == "postgres"
