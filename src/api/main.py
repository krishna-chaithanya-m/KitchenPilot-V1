"""FastAPI Application Main Entrypoint for KitchenPilot-V1.

Provides REST API endpoints for personalized Indian recipe recommendations,
recipe catalog search, and deterministic nutrition profiling.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.config import (
    ALLOWED_ORIGINS,
    CORS_ALLOW_CREDENTIALS,
    ENVIRONMENT,
    LOG_LEVEL,
)
from src.api.dependencies import RecipeStore
from src.api.routes import health, recipes, recommendations
from src.recommendation.recommender import KitchenPilotRecommender

# Configure server-side logging with configurable level
numeric_log_level = getattr(logging, LOG_LEVEL, logging.INFO)
logging.basicConfig(
    level=numeric_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kitchenpilot.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI Lifespan: Load recommendation model and catalog once at startup."""
    logger.info("Initializing KitchenPilot-V1 API in '%s' environment...", ENVIRONMENT)
    logger.info("Configured CORS allowed origins: %s", ALLOWED_ORIGINS)
    try:
        # Load recommendation engine once
        recommender = KitchenPilotRecommender()
        app.state.recommender = recommender

        # Load indexed recipe and nutrition catalog once
        recipe_store = RecipeStore()
        app.state.recipe_store = recipe_store

        logger.info(
            "KitchenPilot-V1 application initialized: %d recipes in catalog.",
            len(recipe_store.recipes_df),
        )
    except Exception as exc:
        logger.exception("Failed to initialize application dependencies: %s", exc)
        raise

    yield

    logger.info("Shutting down KitchenPilot-V1 backend application...")


# FastAPI Application instance
app = FastAPI(
    title="KitchenPilot-V1 API",
    description="Personalized Indian Recipe Recommendation API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware with strict credential handling
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# Exception handlers to prevent leaking stack traces or internal paths
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Format Pydantic 422 validation errors cleanly."""
    logger.info("Validation rejected for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """Format HTTP exceptions cleanly without stack trace leakage."""
    if exc.status_code >= 500:
        logger.error(
            "HTTP %d error for %s %s: %s",
            exc.status_code,
            request.method,
            request.url.path,
            exc.detail,
        )
    elif exc.status_code == status.HTTP_404_NOT_FOUND:
        logger.info(
            "Resource not found for %s %s: %s",
            request.method,
            request.url.path,
            exc.detail,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all 500 handler avoiding stack trace exposure to clients."""
    logger.exception(
        "Unhandled server exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal server error occurred."},
    )


# Register route modules
app.include_router(health.router)
app.include_router(recipes.router)
app.include_router(recommendations.router)
