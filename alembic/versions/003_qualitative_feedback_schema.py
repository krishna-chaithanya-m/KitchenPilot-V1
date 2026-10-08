"""Add qualitative_feedback table for real pilot participant UX feedback.

Revision ID: 003_qualitative_feedback_schema
Revises: 9ee7090d2edc
Create Date: 2026-10-08 17:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_qualitative_feedback_schema"
down_revision: Union[str, None] = "9ee7090d2edc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qualitative_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.String(length=16), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("issue_type", sa.String(length=64), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.recipe_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_qualitative_feedback_user_id", "qualitative_feedback", ["user_id"])
    op.create_index("ix_qualitative_feedback_recipe_id", "qualitative_feedback", ["recipe_id"])
    op.create_index("ix_qualitative_feedback_session_id", "qualitative_feedback", ["session_id"])
    op.create_index("ix_qualitative_feedback_issue_type", "qualitative_feedback", ["issue_type"])
    op.create_index("ix_qualitative_feedback_created_at", "qualitative_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_table("qualitative_feedback")
