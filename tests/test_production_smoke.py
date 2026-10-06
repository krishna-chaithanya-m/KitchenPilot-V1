"""Test suite validating end-to-end production smoke flow (Stage J)."""

from __future__ import annotations

import pytest
from scripts.production_smoke_test import run_smoke_test


def test_production_smoke_workflow():
    """Execute complete 13-step deterministic smoke test workflow."""
    exit_code = run_smoke_test()
    assert exit_code == 0, "Production smoke test workflow failed"
