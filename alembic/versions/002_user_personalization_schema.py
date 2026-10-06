"""Add user personalization, preferences, pantry, feedback, and history tables.

Revision ID: 002_user_personalization_schema
Revises: 001_initial_schema
Create Date: 2026-10-03 23:50:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_user_personalization_schema"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. user_preferences table
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("vegetarian", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("vegan", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("jain", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("satvik", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("preferred_cuisines", sa.JSON(), nullable=False),
        sa.Column("preferred_regions", sa.JSON(), nullable=False),
        sa.Column("preferred_meal_types", sa.JSON(), nullable=False),
        sa.Column("preferred_categories", sa.JSON(), nullable=False),
        sa.Column("preferred_ingredients", sa.JSON(), nullable=False),
        sa.Column("disliked_ingredients", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"], unique=True)

    # 3. user_nutrition_targets table
    op.create_table(
        "user_nutrition_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("target_calories", sa.Float(), nullable=True),
        sa.Column("min_calories", sa.Float(), nullable=True),
        sa.Column("max_calories", sa.Float(), nullable=True),
        sa.Column("target_protein", sa.Float(), nullable=True),
        sa.Column("min_protein", sa.Float(), nullable=True),
        sa.Column("max_protein", sa.Float(), nullable=True),
        sa.Column("target_carbs", sa.Float(), nullable=True),
        sa.Column("min_carbs", sa.Float(), nullable=True),
        sa.Column("max_carbs", sa.Float(), nullable=True),
        sa.Column("target_fat", sa.Float(), nullable=True),
        sa.Column("min_fat", sa.Float(), nullable=True),
        sa.Column("max_fat", sa.Float(), nullable=True),
        sa.Column("target_fiber", sa.Float(), nullable=True),
        sa.Column("min_fiber", sa.Float(), nullable=True),
        sa.Column("max_fiber", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_nutrition_targets_user_id", "user_nutrition_targets", ["user_id"], unique=True)

    # 4. user_pantry table
    op.create_table(
        "user_pantry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.String(length=16), nullable=True),
        sa.Column("ingredient_name", sa.String(length=256), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="IN_STOCK"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.ingredient_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "ingredient_name", name="uq_user_pantry_user_ingredient"),
    )
    op.create_index("ix_user_pantry_user_id", "user_pantry", ["user_id"])
    op.create_index("ix_user_pantry_ingredient_id", "user_pantry", ["ingredient_id"])

    # 5. user_feedback table
    op.create_table(
        "user_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.String(length=16), nullable=False),
        sa.Column("feedback_type", sa.String(length=32), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.recipe_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "recipe_id", "feedback_type", name="uq_user_recipe_feedback"),
    )
    op.create_index("ix_user_feedback_user_id", "user_feedback", ["user_id"])
    op.create_index("ix_user_feedback_recipe_id", "user_feedback", ["recipe_id"])
    op.create_index("ix_user_feedback_feedback_type", "user_feedback", ["feedback_type"])
    op.create_index("ix_user_feedback_user_recipe", "user_feedback", ["user_id", "recipe_id"])

    # 6. recommendation_history table
    op.create_table(
        "recommendation_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("recipe_id", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("ranking_method", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("personalization_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("base_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("personalization_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("final_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("context_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.recipe_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendation_history_user_id", "recommendation_history", ["user_id"])
    op.create_index("ix_recommendation_history_session_id", "recommendation_history", ["session_id"])
    op.create_index("ix_recommendation_history_created_at", "recommendation_history", ["created_at"])


def downgrade() -> None:
    op.drop_table("recommendation_history")
    op.drop_table("user_feedback")
    op.drop_table("user_pantry")
    op.drop_table("user_nutrition_targets")
    op.drop_table("user_preferences")
    op.drop_table("users")
