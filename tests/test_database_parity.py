"""Tests for database parity validation logic and graceful offline handling."""

import pytest
from src.db.session import check_db_connection
from src.db.config import get_database_url
from scripts.validate_database_parity import canonical_fingerprint, ParityValidator


def test_canonical_fingerprint_deterministic():
    """Verify canonical fingerprint produces consistent SHA-256 regardless of key order."""
    dict_a = {"b": 2.00001, "a": "hello", "c": None}
    dict_b = {"a": "hello", "c": None, "b": 2.00004}

    # At float_tol=4, 2.00001 and 2.00004 round to 2.0000
    fp_a = canonical_fingerprint(dict_a, float_tol=4)
    fp_b = canonical_fingerprint(dict_b, float_tol=4)
    assert fp_a == fp_b


def test_parity_validator_offline_handling():
    """Verify ParityValidator check_db_connection reports offline without unhandled crashes."""
    db_url = "postgresql+psycopg://dummy:dummy@localhost:59999/dummy_db"
    is_live, err = check_db_connection(db_url)
    assert not is_live
    assert err is not None


def test_live_database_parity_if_connected():
    """Run full parity validation only if PostgreSQL is live and configured."""
    db_url = get_database_url()
    is_live, _ = check_db_connection(db_url)
    if not is_live:
        pytest.skip("PostgreSQL is not live at configured DATABASE_URL; skipping live parity test.")

    validator = ParityValidator(db_url)
    assert validator.run_all() is True
