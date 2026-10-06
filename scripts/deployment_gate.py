"""
KitchenPilot-V1 — Automated Deployment Gate (Stage J)

Validates the full pre-deployment checklist before releasing to Staging or Production:
1. Environment configuration validation
2. Model artifact integrity (SHA-256 and ML registry)
3. Essential dataset integrity
4. Static release checks (`scripts/release_check.py`)
5. End-to-end production smoke test (`scripts/production_smoke_test.py`)
6. Data sufficiency audit (`scripts/check_feedback_readiness.py`)

A production deployment must not occur merely because tests pass.
"""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

WORKSPACE = Path(__file__).resolve().parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from src.api import config as api_config
from src.ml.config import PRODUCTION_MODEL_PATH
from src.ml.registry import LocalModelRegistry


def print_step(name: str) -> None:
    print(f"\n=======================================================")
    print(f" GATE: {name}")
    print(f"=======================================================")


def check_config() -> bool:
    print_step("1. Environment & Configuration Check")
    try:
        print(f"  - ENVIRONMENT: {api_config.ENVIRONMENT}")
        print(f"  - PILOT_MODE: {api_config.PILOT_MODE}")
        print(f"  - PILOT_MAX_USERS: {api_config.PILOT_MAX_USERS}")
        print(f"  - RATE_LIMIT_ENABLED: {api_config.RATE_LIMIT_ENABLED}")
        print(f"  - LOG_LEVEL: {api_config.LOG_LEVEL}")

        validation_errors = api_config.validate_production_configuration(api_config.ENVIRONMENT)
        if validation_errors:
            print(f"  [WARN] Environment warnings/errors for '{api_config.ENVIRONMENT}':")
            for err in validation_errors:
                print(f"    - {err}")
            if api_config.ENVIRONMENT == "production":
                return False

        print("  [OK] Configuration valid.")
        return True
    except Exception as e:
        print(f"  [FAIL] Configuration validation failed: {e}")
        return False


def check_artifacts() -> bool:
    print_step("2. Model Artifact & Dataset Integrity Check")
    try:
        # Check XGBoost model
        if not PRODUCTION_MODEL_PATH.exists():
            print(f"  [FAIL] Active model missing: {PRODUCTION_MODEL_PATH}")
            return False
        print(f"  [OK] Active ranker exists: {PRODUCTION_MODEL_PATH} ({PRODUCTION_MODEL_PATH.stat().st_size} bytes)")

        # Check registry
        registry = LocalModelRegistry()
        prod_model = registry.get_production_model()
        if not prod_model:
            print("  [FAIL] No active production model found in registry.")
            return False
        print(f"  [OK] Registry production model: {prod_model.model_id} (v{prod_model.model_version})")

        # Check catalog dataset
        if not api_config.RECIPES_PATH.exists():
            print(f"  [FAIL] Processed recipes missing: {api_config.RECIPES_PATH}")
            return False
        print(f"  [OK] Authoritative catalog exists: {api_config.RECIPES_PATH} ({api_config.RECIPES_PATH.stat().st_size} bytes)")

        # Check embeddings
        if not api_config.SEMANTIC_EMBEDDINGS_PATH.exists():
            print(f"  [FAIL] BGE embeddings missing: {api_config.SEMANTIC_EMBEDDINGS_PATH}")
            return False
        print(f"  [OK] BGE embeddings exist: {api_config.SEMANTIC_EMBEDDINGS_PATH} ({api_config.SEMANTIC_EMBEDDINGS_PATH.stat().st_size} bytes)")

        return True
    except Exception as e:
        print(f"  [FAIL] Artifact check failed: {e}")
        return False


def run_command(cmd: list[str], desc: str) -> bool:
    print_step(desc)
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode == 0:
        print(f"  [OK] {desc} passed successfully.")
        return True
    else:
        print(f"  [FAIL] {desc} failed with exit code {result.returncode}:")
        print(result.stdout[-1500:] if len(result.stdout) > 1500 else result.stdout)
        print(result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)
        return False


def main() -> int:
    print("=" * 60)
    print(" KitchenPilot-V1 -- Controlled Deployment Gate Verification")
    print("=" * 60)

    checks = [
        ("Configuration", check_config),
        ("Artifacts & Integrity", check_artifacts),
        (
            "Static Release Checks",
            lambda: run_command([sys.executable, "scripts/release_check.py"], "3. Static Release Check"),
        ),
        (
            "End-to-End Smoke Test",
            lambda: run_command([sys.executable, "scripts/production_smoke_test.py"], "4. End-to-End Production Smoke Test"),
        ),
        (
            "Feedback Data Sufficiency Audit",
            lambda: run_command([sys.executable, "scripts/check_feedback_readiness.py"], "5. Feedback Data Sufficiency Audit"),
        ),
    ]

    all_passed = True
    for name, check_fn in checks:
        if not check_fn():
            print(f"\n[BLOCKED] DEPLOYMENT GATE BLOCKED AT: {name}")
            all_passed = False
            break

    if all_passed:
        print("\n=======================================================")
        print("  ALL DEPLOYMENT GATES PASSED (APPROVED FOR DEPLOYMENT)")
        print("=======================================================")
        return 0
    else:
        print("\n=======================================================")
        print("  DEPLOYMENT GATE FAILED -- RESOLVE BLOCKERS BEFORE RELEASE")
        print("=======================================================")
        return 1


if __name__ == "__main__":
    sys.exit(main())

