"""Unit and integration tests for SQLAlchemy database models and schema definitions."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase

from src.db.base import Base
from src.db.models import (
    RecipeModel,
    IngredientModel,
    IngredientAliasModel,
    RecipeIngredientModel,
    RecipeNutritionModel,
    RecipeIngredientNutritionModel,
    DatasetManifestMetadataModel,
)


def test_models_registered_in_metadata():
    """Verify all 7 production models are registered in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "recipes",
        "ingredients",
        "ingredient_aliases",
        "recipe_ingredients",
        "recipe_nutrition",
        "recipe_ingredient_nutrition",
        "dataset_manifest_metadata",
    }
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"


def test_recipe_model_columns_and_constraints():
    """Verify RecipeModel primary key, required columns, and indexes."""
    table = RecipeModel.__table__
    assert table.c.recipe_id.primary_key
    assert not table.c.recipe_name.nullable
    assert table.c.instructions.nullable  # 6 recipes have null instructions

    index_names = {idx.name for idx in table.indexes}
    assert "ix_recipes_recipe_name" in index_names
    assert "ix_recipes_cuisine" in index_names
    assert "ix_recipes_diet_type" in index_names


def test_ingredient_model_columns_and_constraints():
    """Verify IngredientModel primary key and indexes."""
    table = IngredientModel.__table__
    assert table.c.ingredient_id.primary_key
    assert not table.c.canonical_name.nullable

    index_names = {idx.name for idx in table.indexes}
    assert "ix_ingredients_canonical_name" in index_names


def test_foreign_key_definitions():
    """Verify explicit referential integrity foreign keys."""
    # recipe_ingredients
    ri_fks = {fk.target_fullname for fk in RecipeIngredientModel.__table__.foreign_keys}
    assert "recipes.recipe_id" in ri_fks
    assert "ingredients.ingredient_id" in ri_fks

    # ingredient_aliases
    ia_fks = {fk.target_fullname for fk in IngredientAliasModel.__table__.foreign_keys}
    assert "ingredients.ingredient_id" in ia_fks

    # recipe_nutrition
    rn_fks = {fk.target_fullname for fk in RecipeNutritionModel.__table__.foreign_keys}
    assert "recipes.recipe_id" in rn_fks

    # recipe_ingredient_nutrition
    rin_fks = {fk.target_fullname for fk in RecipeIngredientNutritionModel.__table__.foreign_keys}
    assert "recipes.recipe_id" in rin_fks


def test_dataset_manifest_metadata_model():
    """Verify dataset manifest metadata table structure."""
    table = DatasetManifestMetadataModel.__table__
    assert table.c.id.primary_key
    assert not table.c.dataset_name.nullable
    assert not table.c.dataset_version.nullable


def test_qualitative_feedback_and_personalization_models():
    """Verify qualitative feedback and user models are registered and structurally sound."""
    from src.personalization.models import QualitativeFeedbackModel, UserModel
    table = QualitativeFeedbackModel.__table__
    assert table.c.id.primary_key
    assert not table.c.user_id.nullable
    assert not table.c.issue_type.nullable
    user_fks = {fk.target_fullname for fk in table.foreign_keys}
    assert "users.id" in user_fks
    assert "recipes.recipe_id" in user_fks


def test_alembic_migration_chain_is_linear():
    """Verify that Alembic migrations form an unbroken linear revision chain."""
    from pathlib import Path
    import importlib.util

    versions_dir = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    migration_files = list(versions_dir.glob("*.py"))
    assert len(migration_files) >= 3

    revisions = {}
    down_revisions = {}
    for mf in migration_files:
        if mf.name.startswith("__"):
            continue
        spec = importlib.util.spec_from_file_location(mf.stem, mf)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rev = getattr(mod, "revision", None)
        down = getattr(mod, "down_revision", None)
        if rev:
            revisions[rev] = mf.name
            down_revisions[rev] = down

    # Verify head is 004_authentication_upgrade_schema and down revision chain leads back to None
    curr = "004_authentication_upgrade_schema"
    assert curr in revisions
    visited = []
    while curr is not None:
        visited.append(curr)
        curr = down_revisions.get(curr)

    assert visited == [
        "004_authentication_upgrade_schema",
        "003_qualitative_feedback_schema",
        "9ee7090d2edc",
        "002_user_personalization_schema",
        "001_initial_schema",
    ]


def test_authentication_upgrade_models_structure_and_constraints():
    """Verify Stage 1 authentication upgrade models: columns, FKs, and unique constraints."""
    from src.personalization.models import (
        UserModel,
        EmailVerificationTokenModel,
        PasswordResetTokenModel,
        FederatedIdentityModel,
    )

    # 1. UserModel extensions
    user_table = UserModel.__table__
    assert "is_verified" in user_table.c
    assert not user_table.c.is_verified.nullable
    assert "auth_provider" in user_table.c
    assert not user_table.c.auth_provider.nullable

    # 2. EmailVerificationTokenModel
    evt_table = EmailVerificationTokenModel.__table__
    assert evt_table.c.id.primary_key
    assert not evt_table.c.user_id.nullable
    assert not evt_table.c.token_hash.nullable
    assert not evt_table.c.expires_at.nullable
    assert evt_table.c.used_at.nullable
    evt_fks = {fk.target_fullname for fk in evt_table.foreign_keys}
    assert "users.id" in evt_fks

    # 3. PasswordResetTokenModel
    prt_table = PasswordResetTokenModel.__table__
    assert prt_table.c.id.primary_key
    assert not prt_table.c.user_id.nullable
    assert not prt_table.c.token_hash.nullable
    assert not prt_table.c.expires_at.nullable
    assert prt_table.c.used_at.nullable
    prt_fks = {fk.target_fullname for fk in prt_table.foreign_keys}
    assert "users.id" in prt_fks

    # 4. FederatedIdentityModel
    fid_table = FederatedIdentityModel.__table__
    assert fid_table.c.id.primary_key
    assert not fid_table.c.user_id.nullable
    assert not fid_table.c.provider.nullable
    assert not fid_table.c.provider_user_id.nullable
    assert not fid_table.c.email.nullable
    fid_fks = {fk.target_fullname for fk in fid_table.foreign_keys}
    assert "users.id" in fid_fks

    # Check unique constraints on federated_identities
    uq_names = {c.name for c in fid_table.constraints if hasattr(c, "columns") and len(c.columns) > 1}
    assert "uq_federated_provider_user" in uq_names
    assert "uq_federated_user_provider" in uq_names


def test_token_hashing_security_properties():
    """Verify hash_token produces deterministic SHA-256 digests and guards against invalid input."""
    import hashlib
    from src.personalization.security import hash_token

    sample = "test_verification_token_secret_12345"
    expected = hashlib.sha256(sample.encode("utf-8")).hexdigest()

    digest1 = hash_token(sample)
    digest2 = hash_token(sample)

    assert digest1 == expected
    assert digest1 == digest2
    assert len(digest1) == 64
    assert digest1 != sample  # Raw token must not equal digest

    # Determinism across different tokens
    diff_digest = hash_token("different_token_value_67890")
    assert diff_digest != digest1

    # Empty or non-string input validation
    with pytest.raises(ValueError):
        hash_token("")
    with pytest.raises(ValueError):
        hash_token(None)  # type: ignore


def test_authentication_upgrade_tables_registered_in_metadata():
    """Verify that email_verification_tokens, password_reset_tokens, and federated_identities are in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected = {"email_verification_tokens", "password_reset_tokens", "federated_identities"}
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"
