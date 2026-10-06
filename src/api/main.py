"""FastAPI Application Main Entrypoint for KitchenPilot-V1.

Provides REST API endpoints for personalized Indian recipe recommendations,
recipe catalog search, and deterministic nutrition profiling.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.config import (
    ALLOWED_ORIGINS,
    CORS_ALLOW_CREDENTIALS,
    ENVIRONMENT,
    LOG_LEVEL,
    validate_production_configuration,
)
from src.api.dependencies import RecipeStore, create_recipe_store
from src.api.middleware import RequestCorrelationAndSecurityMiddleware
from src.api.routes import auth, health, recipes, recommendations, user
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
    """FastAPI Lifespan: Validate config, load recommendation model and catalog once at startup."""
    logger.info("Initializing KitchenPilot-V1 API in '%s' environment...", ENVIRONMENT)
    logger.info("Configured CORS allowed origins: %s", ALLOWED_ORIGINS)

    # Validate production configuration if running in production mode
    config_errors = validate_production_configuration()
    if config_errors:
        for err in config_errors:
            logger.error("Configuration validation error: %s", err)
        if ENVIRONMENT == "production":
            raise RuntimeError(f"Production configuration validation failed: {'; '.join(config_errors)}")

    try:
        # Load recommendation engine once
        recommender = KitchenPilotRecommender()
        app.state.recommender = recommender

        # Load indexed recipe and nutrition catalog once via repository abstraction
        recipe_store = create_recipe_store()
        app.state.recipe_store = recipe_store

        catalog_count = (
            len(recipe_store.recipes_df)
            if hasattr(recipe_store, "recipes_df")
            else "PostgreSQL"
        )
        logger.info(
            "KitchenPilot-V1 application initialized: %s recipes in catalog.",
            catalog_count,
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

# Request correlation, rate limiting, and security header middleware (outermost)
app.add_middleware(RequestCorrelationAndSecurityMiddleware)

# CORS middleware with strict credential handling
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


# Exception handlers to prevent leaking stack traces or internal paths
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Format Pydantic 422 validation errors cleanly with request ID."""
    req_id = getattr(request.state, "request_id", "unknown")
    logger.info("[%s] Validation rejected for %s %s", req_id, request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        headers={"X-Request-ID": req_id},
        content={
            "detail": jsonable_encoder(exc.errors()),
            "request_id": req_id,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """Format HTTP exceptions cleanly without stack trace leakage."""
    req_id = getattr(request.state, "request_id", "unknown")
    if exc.status_code >= 500:
        logger.error(
            "[%s] HTTP %d error for %s %s: %s",
            req_id,
            exc.status_code,
            request.method,
            request.url.path,
            exc.detail,
        )
    elif exc.status_code == status.HTTP_404_NOT_FOUND:
        logger.info(
            "[%s] Resource not found for %s %s: %s",
            req_id,
            request.method,
            request.url.path,
            exc.detail,
        )
    headers = {"X-Request-ID": req_id}
    if exc.headers:
        headers.update(exc.headers)
    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={"detail": exc.detail, "request_id": req_id},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all 500 handler avoiding stack trace exposure to clients."""
    req_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "[%s] Unhandled server exception on %s %s: %s",
        req_id,
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers={"X-Request-ID": req_id},
        content={
            "detail": "An unexpected internal server error occurred.",
            "request_id": req_id,
        },
    )


# Register route modules
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(recipes.router)
app.include_router(recommendations.router)
