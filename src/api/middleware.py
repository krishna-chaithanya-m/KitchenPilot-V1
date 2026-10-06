"""Request correlation ID, rate limiting, and structured logging middleware for KitchenPilot-V1."""

from __future__ import annotations

import json
import logging
import re
import secrets
import time
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.config import (
    ENVIRONMENT,
    RATE_LIMIT_AUTH_RPM,
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_FEEDBACK_RPM,
    RATE_LIMIT_GLOBAL_RPM,
    RATE_LIMIT_RECOMMEND_RPM,
    STRUCTURED_LOGGING,
)

logger = logging.getLogger("kitchenpilot.access")


class MetricsCollector:
    """Application metrics and product KPI tracker for Stage J operational readiness."""

    def __init__(self) -> None:
        # Request & error counters
        self.total_requests: int = 0
        self.total_errors: int = 0
        self.status_codes: Dict[int, int] = defaultdict(int)
        self.endpoint_latencies_ms: Dict[str, List[float]] = defaultdict(list)
        self.recommendation_types: Dict[str, int] = defaultdict(int)
        self.feedback_counts: Dict[str, int] = defaultdict(int)
        self.fallbacks_triggered: int = 0

        # Stage J User Metrics
        self.registrations: int = 0
        self.logins: int = 0
        self.active_users: set = set()
        self.user_login_counts: Dict[str, int] = defaultdict(int)

        # Stage J Recommendation Metrics
        self.recommendation_requests: int = 0
        self.successful_recommendations: int = 0
        self.failed_recommendations: int = 0
        self.zero_result_recommendations: int = 0
        self.candidates_retrieved_history: List[int] = []
        self.recommendations_returned_history: List[int] = []

        # Stage J System & Stage Latencies (ms)
        self.db_latencies_ms: List[float] = []
        self.retrieval_latencies_ms: List[float] = []
        self.constraint_latencies_ms: List[float] = []
        self.ranking_latencies_ms: List[float] = []

        # Stage J Engagement Metrics
        self.impressions_count: int = 0
        self.likes_count: int = 0
        self.saves_count: int = 0
        self.cooked_count: int = 0
        self.dislikes_count: int = 0
        self.hides_count: int = 0

    def record_request(self, endpoint: str, status_code: int, latency_ms: float) -> None:
        self.total_requests += 1
        self.status_codes[status_code] += 1
        if status_code >= 400:
            self.total_errors += 1
        # Keep sliding buffer of last 500 latencies per endpoint to bound memory
        lats = self.endpoint_latencies_ms[endpoint]
        lats.append(latency_ms)
        if len(lats) > 500:
            self.endpoint_latencies_ms[endpoint] = lats[-500:]

    def record_registration(self) -> None:
        self.registrations += 1

    def record_login(self, user_id: Optional[object] = None) -> None:
        self.logins += 1
        if user_id is not None:
            uid_str = str(user_id)
            self.active_users.add(uid_str)
            self.user_login_counts[uid_str] += 1

    def record_recommendation(self, mode: str) -> None:
        self.recommendation_types[mode] += 1

    def record_recommendation_event(
        self,
        success: bool,
        zero_results: bool = False,
        candidates_retrieved: int = 0,
        returned_count: int = 0,
        retrieval_ms: float = 0.0,
        constraint_ms: float = 0.0,
        ranking_ms: float = 0.0,
    ) -> None:
        self.recommendation_requests += 1
        if success:
            self.successful_recommendations += 1
        else:
            self.failed_recommendations += 1

        if zero_results:
            self.zero_result_recommendations += 1

        self.candidates_retrieved_history.append(candidates_retrieved)
        if len(self.candidates_retrieved_history) > 500:
            self.candidates_retrieved_history = self.candidates_retrieved_history[-500:]

        self.recommendations_returned_history.append(returned_count)
        if len(self.recommendations_returned_history) > 500:
            self.recommendations_returned_history = self.recommendations_returned_history[-500:]

        if retrieval_ms > 0:
            self.retrieval_latencies_ms.append(retrieval_ms)
            if len(self.retrieval_latencies_ms) > 500:
                self.retrieval_latencies_ms = self.retrieval_latencies_ms[-500:]

        if constraint_ms > 0:
            self.constraint_latencies_ms.append(constraint_ms)
            if len(self.constraint_latencies_ms) > 500:
                self.constraint_latencies_ms = self.constraint_latencies_ms[-500:]

        if ranking_ms > 0:
            self.ranking_latencies_ms.append(ranking_ms)
            if len(self.ranking_latencies_ms) > 500:
                self.ranking_latencies_ms = self.ranking_latencies_ms[-500:]

    def record_impression(self, count: int = 1) -> None:
        self.impressions_count += max(0, count)

    def record_feedback(self, feedback_type: str) -> None:
        fb_upper = feedback_type.upper().strip()
        self.feedback_counts[fb_upper] += 1
        if fb_upper == "LIKE":
            self.likes_count += 1
        elif fb_upper == "SAVE":
            self.saves_count += 1
        elif fb_upper == "COOKED":
            self.cooked_count += 1
        elif fb_upper == "DISLIKE":
            self.dislikes_count += 1
        elif fb_upper == "HIDE":
            self.hides_count += 1

    def record_db_latency(self, latency_ms: float) -> None:
        self.db_latencies_ms.append(latency_ms)
        if len(self.db_latencies_ms) > 500:
            self.db_latencies_ms = self.db_latencies_ms[-500:]

    def record_fallback(self) -> None:
        self.fallbacks_triggered += 1

    @staticmethod
    def _percentile(values: List[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(p * len(sorted_vals))
        return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 2)

    def get_summary(self) -> Dict[str, object]:
        endpoint_stats = {}
        all_request_latencies: List[float] = []
        for ep, lats in self.endpoint_latencies_ms.items():
            all_request_latencies.extend(lats)
            if lats:
                sorted_lats = sorted(lats)
                n = len(sorted_lats)
                p95_idx = int(0.95 * n)
                p99_idx = int(0.99 * n)
                endpoint_stats[ep] = {
                    "count": n,
                    "avg_ms": round(sum(sorted_lats) / n, 2),
                    "p50_ms": round(sorted_lats[n // 2], 2),
                    "p95_ms": round(sorted_lats[min(p95_idx, n - 1)], 2),
                    "p99_ms": round(sorted_lats[min(p99_idx, n - 1)], 2),
                }

        returning_users = sum(1 for cnt in self.user_login_counts.values() if cnt > 1)
        avg_cand = (
            round(sum(self.candidates_retrieved_history) / len(self.candidates_retrieved_history), 2)
            if self.candidates_retrieved_history
            else 0.0
        )
        avg_rec = (
            round(sum(self.recommendations_returned_history) / len(self.recommendations_returned_history), 2)
            if self.recommendations_returned_history
            else 0.0
        )
        total_engagements = (
            self.likes_count + self.saves_count + self.cooked_count + self.dislikes_count + self.hides_count
        )

        return {
            # Backward-compatible Stage H keys
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": round(self.total_errors / self.total_requests, 4) if self.total_requests > 0 else 0.0,
            "status_codes": dict(self.status_codes),
            "recommendation_types": dict(self.recommendation_types),
            "feedback_counts": dict(self.feedback_counts),
            "fallbacks_triggered": self.fallbacks_triggered,
            "endpoint_latencies": endpoint_stats,
            # Stage J Product KPIs
            "user_kpis": {
                "registrations": self.registrations,
                "successful_logins": self.logins,
                "active_users": len(self.active_users),
                "returning_users": returning_users,
            },
            "recommendation_kpis": {
                "recommendation_requests": self.recommendation_requests,
                "successful_recommendations": self.successful_recommendations,
                "failed_recommendations": self.failed_recommendations,
                "zero_result_recommendations": self.zero_result_recommendations,
                "zero_result_rate": (
                    round(self.zero_result_recommendations / self.recommendation_requests, 4)
                    if self.recommendation_requests > 0
                    else 0.0
                ),
                "average_candidates_retrieved": avg_cand,
                "average_final_recommendations": avg_rec,
            },
            "engagement_kpis": {
                "impressions": self.impressions_count,
                "likes": self.likes_count,
                "saves": self.saves_count,
                "cooked": self.cooked_count,
                "dislikes": self.dislikes_count,
                "hides": self.hides_count,
                "total_engagements": total_engagements,
            },
            "funnel_kpis": {
                "recommendation_request": self.recommendation_requests,
                "impression": self.impressions_count,
                "engagement": total_engagements,
                "save": self.saves_count,
                "cook": self.cooked_count,
            },
            "system_kpis": {
                "request_latency_p50_ms": self._percentile(all_request_latencies, 0.50),
                "request_latency_p95_ms": self._percentile(all_request_latencies, 0.95),
                "error_rate": round(self.total_errors / self.total_requests, 4) if self.total_requests > 0 else 0.0,
                "database_latency_p50_ms": self._percentile(self.db_latencies_ms, 0.50),
                "database_latency_p95_ms": self._percentile(self.db_latencies_ms, 0.95),
                "retrieval_latency_p50_ms": self._percentile(self.retrieval_latencies_ms, 0.50),
                "retrieval_latency_p95_ms": self._percentile(self.retrieval_latencies_ms, 0.95),
                "constraint_filtering_latency_p50_ms": self._percentile(self.constraint_latencies_ms, 0.50),
                "constraint_filtering_latency_p95_ms": self._percentile(self.constraint_latencies_ms, 0.95),
                "ranking_latency_p50_ms": self._percentile(self.ranking_latencies_ms, 0.50),
                "ranking_latency_p95_ms": self._percentile(self.ranking_latencies_ms, 0.95),
            },
        }


# Global metrics collector singleton
metrics_collector = MetricsCollector()


class InMemoryRateLimiter:
    """Lightweight in-memory sliding-window rate limiter per client IP."""

    def __init__(self) -> None:
        # Map: (ip, route_key) -> list of timestamp floats
        self._history: Dict[Tuple[str, str], List[float]] = defaultdict(list)

    def check_rate_limit(self, client_ip: str, path: str) -> Tuple[bool, int]:
        """Check if request exceeds rate limit. Returns (is_allowed, retry_after_seconds)."""
        now = time.time()
        window_size = 60.0  # 1 minute

        # Determine limit by route family
        if "/api/v1/auth" in path:
            limit = RATE_LIMIT_AUTH_RPM
            route_key = "auth"
        elif "/api/v1/recommend" in path:
            limit = RATE_LIMIT_RECOMMEND_RPM
            route_key = "recommend"
        elif "/api/v1/user/feedback" in path:
            limit = RATE_LIMIT_FEEDBACK_RPM
            route_key = "feedback"
        else:
            limit = RATE_LIMIT_GLOBAL_RPM
            route_key = "global"

        key = (client_ip, route_key)
        timestamps = self._history[key]
        # Prune events older than 60s
        cutoff = now - window_size
        valid = [t for t in timestamps if t > cutoff]
        self._history[key] = valid

        if len(valid) >= limit:
            oldest = valid[0]
            retry_after = int(max(1.0, 60.0 - (now - oldest)))
            return False, retry_after

        self._history[key].append(now)
        return True, 0


rate_limiter = InMemoryRateLimiter()


class RequestCorrelationAndSecurityMiddleware(BaseHTTPMiddleware):
    """Handles Request ID correlation, security headers, structured logging, and rate limiting."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()

        # 1. Request ID (honor incoming X-Request-ID or generate new req_<hex12>)
        request_id = request.headers.get("X-Request-ID")
        if not request_id or not re.match(r"^[a-zA-Z0-9_\-\.]{4,64}$", request_id):
            request_id = f"req_{secrets.token_hex(8)}"
        request.state.request_id = request_id

        # 2. Rate limiting check
        client_ip = request.client.host if request.client else "127.0.0.1"
        if RATE_LIMIT_ENABLED and not request.url.path.startswith("/api/v1/health"):
            allowed, retry_after = rate_limiter.check_rate_limit(client_ip, request.url.path)
            if not allowed:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={
                        "X-Request-ID": request_id,
                        "Retry-After": str(retry_after),
                    },
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                            "request_id": request_id,
                        }
                    },
                )

        # 3. Process the request
        try:
            response = await call_next(request)
        except Exception as exc:
            # Caught by FastAPI exception handlers, but in case of low-level bubble
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            metrics_collector.record_request(request.url.path, 500, latency_ms)
            raise exc

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # 4. Attach security headers and correlation ID to response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 5. Record metrics
        metrics_collector.record_request(request.url.path, response.status_code, latency_ms)

        # 6. Structured logging
        if STRUCTURED_LOGGING:
            log_record = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "level": "INFO" if response.status_code < 400 else ("WARN" if response.status_code < 500 else "ERROR"),
                "logger": "kitchenpilot.api",
                "event": "http_request",
                "request_id": request_id,
                "client_ip": client_ip,
                "method": request.method,
                "route": request.url.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            }
            logger.info(json.dumps(log_record))
        else:
            logger.info(
                "[%s] %s %s - %d (%.2fms)",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                latency_ms,
            )

        return response
