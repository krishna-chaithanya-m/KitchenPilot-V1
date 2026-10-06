"""Health and Readiness Probes for KitchenPilot-V1 API."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from src.api.config import (
    INGREDIENTS_PATH,
    RECIPE_CORPUS_PATH,
    RECIPE_INDEX_PATH,
    RECIPE_INGREDIENTS_LINKED_PATH,
    RECIPE_NUTRITION_PATH,
    RECIPES_PATH,
    SEMANTIC_EMBEDDINGS_PATH,
    SEMANTIC_RETRIEVAL_ENABLED,
    TFIDF_MATRIX_PATH,
    TFIDF_VECTORIZER_PATH,
    XGBOOST_MODEL_PATH,
    XGBOOST_RANKING_ENABLED,
    validate_production_configuration,
)
from src.api.middleware import metrics_collector
from src.api.schemas import HealthResponse, ReadinessResponse
from src.db.config import is_postgres_backend
from src.db.session import check_db_connection

router = APIRouter(prefix="/api/v1", tags=["Health & Readiness"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service Health Check",
    description="Returns standard operational health status of the KitchenPilot-V1 API service.",
)
def get_health() -> HealthResponse:
    """Return service operational health status."""
    return HealthResponse(status="ok", service="KitchenPilot-V1", version="1.0.0")


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness Probe",
    description="Verifies that recommendation artifacts, corpus, processed datasets, and required dependencies exist and are accessible.",
)
def get_readiness(response: Response) -> ReadinessResponse:
    """Verify system readiness across model artifacts, corpus, configuration, and processed data."""
    models_exist = (
        TFIDF_VECTORIZER_PATH.is_file()
        and TFIDF_MATRIX_PATH.is_file()
        and RECIPE_INDEX_PATH.is_file()
    )
    corpus_exists = RECIPE_CORPUS_PATH.is_file()
    data_exists = (
        RECIPES_PATH.is_file()
        and RECIPE_NUTRITION_PATH.is_file()
        and RECIPE_INGREDIENTS_LINKED_PATH.is_file()
        and INGREDIENTS_PATH.is_file()
    )

    if is_postgres_backend():
        backend_ready, _ = check_db_connection(timeout_seconds=2)
    else:
        backend_ready = data_exists

    # Check optional components if enabled
    semantic_ready = not SEMANTIC_RETRIEVAL_ENABLED or SEMANTIC_EMBEDDINGS_PATH.is_file()
    xgboost_ready = not XGBOOST_RANKING_ENABLED or XGBOOST_MODEL_PATH.is_file()
    config_errors = validate_production_configuration()
    config_valid = len(config_errors) == 0

    all_ready = models_exist and corpus_exists and backend_ready and semantic_ready and xgboost_ready and config_valid
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        status_text = "not_ready"
    else:
        status_text = "ready"

    return ReadinessResponse(
        status=status_text,
        service="KitchenPilot-V1",
        version="1.0.0",
        checks={
            "model_artifacts": models_exist,
            "recipe_corpus": corpus_exists,
            "processed_data": data_exists,
            "database_connectivity": backend_ready,
            "semantic_artifacts": semantic_ready,
            "xgboost_artifacts": xgboost_ready,
            "configuration_valid": config_valid,
        },
    )


@router.get(
    "/metrics",
    summary="Application Observability Metrics",
    description="Exposes in-memory operational metrics for API latency, request counts, recommendation modes, and fallbacks.",
)
def get_metrics() -> dict:
    """Return aggregated application and pipeline metrics."""
    return metrics_collector.get_summary()
