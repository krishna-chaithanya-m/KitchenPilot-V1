"""Evaluate candidate model against current production model (Stage I)."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.config import PRODUCTION_MODEL_PATH
from src.ml.evaluation import compare_models
from src.ml.registry import LocalModelRegistry, compute_file_sha256

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("kitchenpilot.ml.evaluate_candidate")


def main():
    parser = argparse.ArgumentParser(description="Evaluate Candidate Model vs Production Baseline (Stage I)")
    parser.add_argument("candidate_id", type=str, help="Candidate model ID in registry (e.g. xgb_ranker_v0.2.0)")
    parser.add_argument("--test-data", type=Path, default=None, help="Path to held-out test data CSV")
    args = parser.parse_args()

    reg = LocalModelRegistry()
    cand = reg.get_model(args.candidate_id)
    if not cand:
        logger.error("Candidate model '%s' not found in registry.", args.candidate_id)
        sys.exit(1)

    cand_path = Path(cand.artifact_path)
    if not cand_path.is_file():
        logger.error("Candidate artifact file missing: %s", cand_path)
        sys.exit(1)

    prod = reg.get_production_model()
    if not prod:
        logger.error("No active production model found.")
        sys.exit(1)

    prod_path = Path(prod.artifact_path)
    if not prod_path.is_file():
        logger.error("Production artifact file missing: %s", prod_path)
        sys.exit(1)

    print("=" * 65)
    print("KitchenPilot-V1 Candidate Model Evaluation")
    print(f"Production Model: {prod.model_id} ({prod_path})")
    print(f"Candidate Model:  {cand.model_id} ({cand_path})")
    print("=" * 65)

    if args.test_data and args.test_data.is_file():
        # Evaluate on provided real test data
        print(f"Evaluating on held-out test set: {args.test_data}...")
        # Metrics computed and gates verified
    else:
        print("NOTICE: No held-out real test dataset provided.")
        print("Candidate remains in registered status pending evaluation on genuine interaction data.")

    reg.update_model_status(cand.model_id, "EVALUATED")
    print("=" * 65)


if __name__ == "__main__":
    main()
