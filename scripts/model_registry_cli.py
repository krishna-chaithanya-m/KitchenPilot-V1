"""CLI utility for Model Registry management, inspections, promotions, and rollbacks (Stage I)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.promotion import promote_candidate_model, rollback_production_model
from src.ml.registry import LocalModelRegistry, compute_file_sha256


def main():
    parser = argparse.ArgumentParser(description="KitchenPilot-V1 Model Registry CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="List all registered models in registry.")

    # production
    subparsers.add_parser("production", help="Show the currently active production model.")

    # show
    show_parser = subparsers.add_parser("show", help="Show details of a specific model.")
    show_parser.add_argument("model_id", type=str, help="Model ID (e.g. xgb_ranker_v0.1.0)")

    # promote
    promote_parser = subparsers.add_parser("promote", help="Explicitly promote an evaluated candidate model.")
    promote_parser.add_argument("model_id", type=str, help="Candidate model ID to promote")
    promote_parser.add_argument("--force", action="store_true", help="Force promotion bypassing evaluation check")

    # rollback
    subparsers.add_parser("rollback", help="Roll back active production model to previous archived model.")

    # validate
    val_parser = subparsers.add_parser("validate", help="Validate artifact file and checksum for a model.")
    val_parser.add_argument("model_id", type=str, help="Model ID to validate")

    args = parser.parse_args()
    reg = LocalModelRegistry()

    if args.command == "list":
        models = reg.list_models()
        print(f"{'MODEL ID':<25} {'VERSION':<10} {'STATUS':<12} {'CHECKSUM':<16} {'CREATED AT':<26}")
        print("-" * 90)
        for m in models:
            print(f"{m.model_id:<25} {m.model_version:<10} {m.status:<12} {m.artifact_checksum[:14]:<16} {m.created_at:<26}")

    elif args.command == "production":
        prod = reg.get_production_model()
        if prod:
            print("=" * 60)
            print("ACTIVE PRODUCTION MODEL")
            print("=" * 60)
            print(f"Model ID:               {prod.model_id}")
            print(f"Model Version:          {prod.model_version}")
            print(f"Status:                 {prod.status}")
            print(f"Artifact Path:          {prod.artifact_path}")
            print(f"SHA-256 Checksum:       {prod.artifact_checksum}")
            print(f"Feature Schema Version: {prod.feature_schema_version}")
            print(f"Dataset Version:        {prod.dataset_version}")
            print(f"Metrics:                {json.dumps(prod.metrics)}")
            print("=" * 60)
        else:
            print("No active production model found.")

    elif args.command == "show":
        m = reg.get_model(args.model_id)
        if m:
            print(json.dumps(m.__dict__, indent=2))
        else:
            print(f"Model '{args.model_id}' not found.")
            sys.exit(1)

    elif args.command == "promote":
        success, msg = promote_candidate_model(args.model_id, registry=reg, force=args.force)
        print(msg)
        sys.exit(0 if success else 1)

    elif args.command == "rollback":
        success, msg = rollback_production_model(registry=reg)
        print(msg)
        sys.exit(0 if success else 1)

    elif args.command == "validate":
        m = reg.get_model(args.model_id)
        if not m:
            print(f"Model '{args.model_id}' not found in registry.")
            sys.exit(1)
        p = Path(m.artifact_path)
        if not p.is_file():
            print(f"[FAIL] Artifact file missing: {p}")
            sys.exit(1)
        actual_sha = compute_file_sha256(p)
        if actual_sha == m.artifact_checksum:
            print(f"[PASS] Artifact valid. Checksum verified: {actual_sha}")
        else:
            print(f"[FAIL] Checksum mismatch: expected {m.artifact_checksum}, got {actual_sha}")
            sys.exit(1)


if __name__ == "__main__":
    main()
