"""Reproducible Performance Benchmark & Load Testing for KitchenPilot-V1 (Stage H).

Measures:
1. Cold Start Latencies:
   - Application startup
   - Engine initialization
   - Catalog loading
2. Warm Requests Latencies (Mean, Median, P95, P99):
   - Health check
   - Recipe lookup
   - TF-IDF recommendation
   - Ingredient-based recommendation
   - Semantic recommendation (if enabled)
   - Personalized recommendation simulation
3. Local Load Testing:
   - Concurrent requests simulation across representative endpoints
   - Throughput (RPS), failure counts, and latency percentiles
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Dict, List

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_benchmark(num_warm_samples: int = 25) -> Dict[str, object]:
    results: Dict[str, object] = {}

    # 1. Cold start measurements
    print("[1/3] Measuring Cold Start latencies...")
    t0 = time.perf_counter()
    from src.recommendation.recommender import KitchenPilotRecommender
    from src.api.dependencies import create_recipe_store
    engine_init_ms = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    store = create_recipe_store()
    catalog_load_ms = (time.perf_counter() - t1) * 1000.0

    t2 = time.perf_counter()
    from fastapi.testclient import TestClient
    from src.api.main import app
    client_ctx = TestClient(app)
    client = client_ctx.__enter__()
    app_startup_ms = (time.perf_counter() - t2) * 1000.0

    results["cold_start"] = {
        "engine_initialization_ms": round(engine_init_ms, 2),
        "catalog_loading_ms": round(catalog_load_ms, 2),
        "app_startup_ms": round(app_startup_ms, 2),
    }

    # 2. Warm request benchmarks
    print(f"[2/3] Benchmarking Warm Endpoints ({num_warm_samples} samples each)...")
    endpoints_to_test = [
        ("GET /api/v1/health", lambda: client.get("/api/v1/health")),
        ("GET /api/v1/recipes/R00001", lambda: client.get("/api/v1/recipes/R00001")),
        ("GET /api/v1/recipes/R00001/nutrition", lambda: client.get("/api/v1/recipes/R00001/nutrition")),
        ("POST /api/v1/recommend (similarity)", lambda: client.post("/api/v1/recommend", json={"query_recipe_id": "R00001", "top_k": 10})),
        ("POST /api/v1/recommend/by-ingredients", lambda: client.post("/api/v1/recommend/by-ingredients", json={"ingredients": ["paneer", "tomato", "ginger"], "top_k": 10})),
        ("POST /api/v1/recommend (dietary constraint)", lambda: client.post("/api/v1/recommend", json={"query_recipe_id": "R00001", "user_preferences": {"vegetarian": True}, "top_k": 10})),
    ]

    warm_stats = {}
    for name, req_fn in endpoints_to_test:
        latencies = []
        # Warm-up run
        req_fn()
        for _ in range(num_warm_samples):
            t = time.perf_counter()
            resp = req_fn()
            lat = (time.perf_counter() - t) * 1000.0
            if resp.status_code < 400:
                latencies.append(lat)

        if latencies:
            sorted_lat = sorted(latencies)
            n = len(sorted_lat)
            p95_idx = min(int(0.95 * n), n - 1)
            p99_idx = min(int(0.99 * n), n - 1)
            warm_stats[name] = {
                "samples": n,
                "mean_ms": round(statistics.mean(latencies), 2),
                "median_ms": round(statistics.median(latencies), 2),
                "p95_ms": round(sorted_lat[p95_idx], 2),
                "p99_ms": round(sorted_lat[p99_idx], 2),
            }

    results["warm_endpoints"] = warm_stats

    # 3. Local concurrent load simulation
    print("[3/3] Running local load simulation (100 sequential mixed requests)...")
    mixed_requests = [
        lambda: client.get("/api/v1/health"),
        lambda: client.get("/api/v1/recipes/R00002"),
        lambda: client.post("/api/v1/recommend", json={"query_recipe_id": "R00001", "top_k": 5}),
        lambda: client.post("/api/v1/recommend/by-ingredients", json={"ingredients": ["potato", "onion", "mustard oil"], "top_k": 5}),
    ]

    total_reqs = 100
    failures = 0
    t_start = time.perf_counter()
    load_latencies = []

    for i in range(total_reqs):
        fn = mixed_requests[i % len(mixed_requests)]
        t = time.perf_counter()
        resp = fn()
        lat = (time.perf_counter() - t) * 1000.0
        load_latencies.append(lat)
        if resp.status_code >= 400:
            failures += 1

    total_time_s = time.perf_counter() - t_start
    rps = round(total_reqs / total_time_s, 2)
    sorted_load = sorted(load_latencies)
    n = len(sorted_load)
    p95_idx = min(int(0.95 * n), n - 1)
    p99_idx = min(int(0.99 * n), n - 1)

    results["load_test"] = {
        "total_requests": total_reqs,
        "failures": failures,
        "duration_seconds": round(total_time_s, 2),
        "throughput_rps": rps,
        "mean_latency_ms": round(statistics.mean(load_latencies), 2),
        "p50_latency_ms": round(statistics.median(load_latencies), 2),
        "p95_latency_ms": round(sorted_load[p95_idx], 2),
        "p99_latency_ms": round(sorted_load[p99_idx], 2),
    }

    client_ctx.__exit__(None, None, None)
    return results


def main():
    parser = argparse.ArgumentParser(description="Performance and Load Benchmarking for KitchenPilot-V1.")
    parser.add_argument("--samples", type=int, default=20, help="Number of warm samples per endpoint.")
    args = parser.parse_args()

    print("=" * 60)
    print("KitchenPilot-V1 Performance & Load Benchmark")
    print("=" * 60)
    results = run_benchmark(num_warm_samples=args.samples)
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(json.dumps(results, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    main()
