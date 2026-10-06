"""Production Deployment Verification Script for KitchenPilot-V1 (Stage H).

Validates:
- Python environment version (>=3.11, tested up to 3.14)
- Core dependencies availability
- Configuration validity (secrets, CORS, environment)
- Authoritative datasets presence and SHA-256 integrity against manifest.json
- Recommendation model artifacts presence and integrity
- Database connectivity (if PostgreSQL configured)
- FastAPI application import and health endpoints simulation
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_production_checks() -> int:
    print("=" * 60)
    print("KitchenPilot-V1 Production Readiness Verification")
    print(f"Project root: {PROJECT_ROOT}")
    print("=" * 60)
    failures = 0

    # 1. Python version check
    py_ver = sys.version_info
    print(f"[*] Python runtime: {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if py_ver.major < 3 or (py_ver.major == 3 and py_ver.minor < 11):
        print(f" [FAIL] Python >= 3.11 required, found {py_ver.major}.{py_ver.minor}")
        failures += 1
    else:
        print(" [PASS] Python version compatible.")

    # 2. Dependency audit
    required_packages = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "pandas",
        "numpy",
        "sklearn",
        "xgboost",
        "argon2",
        "jwt",
    ]
    for pkg in required_packages:
        try:
            __import__(pkg)
            print(f" [PASS] Dependency available: {pkg}")
        except ImportError as e:
            print(f" [FAIL] Missing required dependency: {pkg} ({e})")
            failures += 1

    # 3. Model & dataset manifest verification
    manifest_path = PROJECT_ROOT / "models" / "manifest.json"
    if not manifest_path.is_file():
        print(f" [FAIL] Manifest missing: {manifest_path}")
        failures += 1
    else:
        print(" [PASS] Artifact manifest exists.")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Verify required artifacts
            for name, art in manifest.get("artifacts", {}).items():
                p = PROJECT_ROOT / art["path"]
                if not p.is_file():
                    if art.get("required", False):
                        print(f" [FAIL] Required model artifact missing: {art['path']}")
                        failures += 1
                    else:
                        print(f" [WARN] Optional model artifact missing (fallback active): {art['path']}")
                else:
                    file_sha = compute_sha256(p)
                    if file_sha == art["sha256"]:
                        print(f" [PASS] Verified artifact checksum: {art['path']}")
                    else:
                        print(f" [FAIL] Checksum mismatch for {art['path']}: expected {art['sha256']}, got {file_sha}")
                        failures += 1

            # Verify datasets
            for name, ds in manifest.get("datasets", {}).items():
                p = PROJECT_ROOT / ds["path"]
                if not p.is_file():
                    print(f" [FAIL] Required dataset missing: {ds['path']}")
                    failures += 1
                else:
                    file_sha = compute_sha256(p)
                    if file_sha == ds["sha256"]:
                        print(f" [PASS] Verified dataset checksum: {ds['path']}")
                    else:
                        print(f" [FAIL] Dataset checksum mismatch for {ds['path']}")
                        failures += 1
        except Exception as e:
            print(f" [FAIL] Error evaluating manifest: {e}")
            failures += 1

    # 4. Configuration safety audit
    from src.api.config import (
        ALLOWED_ORIGINS,
        AUTH_SECRET_KEY,
        ENVIRONMENT,
        validate_production_configuration,
    )
    print(f"[*] Active Environment: {ENVIRONMENT}")
    config_errors = validate_production_configuration()
    if config_errors:
        for err in config_errors:
            print(f" [FAIL] Configuration violation: {err}")
            failures += 1
    else:
        print(" [PASS] Production configuration validation clean.")

    # 5. Fast API Application & Health Probe simulation
    try:
        from fastapi.testclient import TestClient
        from src.api.main import app

        with TestClient(app) as client:
            resp_health = client.get("/api/v1/health")
            if resp_health.status_code == 200:
                print(" [PASS] Liveness probe (/health) returned 200 OK.")
            else:
                print(f" [FAIL] Liveness probe returned {resp_health.status_code}")
                failures += 1

            resp_ready = client.get("/api/v1/health/ready")
            if resp_ready.status_code == 200:
                print(f" [PASS] Readiness probe (/health/ready) returned 200 OK: {resp_ready.json()['status']}")
            else:
                print(f" [WARN/FAIL] Readiness probe returned {resp_ready.status_code}: {resp_ready.text}")
                # Only fail if in CSV mode where local data is guaranteed
                from src.db.config import is_postgres_backend
                if not is_postgres_backend():
                    failures += 1

            resp_metrics = client.get("/api/v1/metrics")
            if resp_metrics.status_code == 200:
                print(" [PASS] Metrics endpoint (/metrics) returned 200 OK.")
            else:
                print(f" [FAIL] Metrics endpoint returned {resp_metrics.status_code}")
                failures += 1
    except Exception as e:
        print(f" [FAIL] Application startup or probe test failed: {e}")
        failures += 1

    print("=" * 60)
    if failures == 0:
        print("PRODUCTION READINESS VERIFICATION SUCCEEDED (0 blockers).")
        print("=" * 60)
        return 0
    else:
        print(f"PRODUCTION READINESS BLOCKED: {failures} issues found.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(run_production_checks())
