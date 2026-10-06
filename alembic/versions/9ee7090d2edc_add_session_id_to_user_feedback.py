"""add session id to user feedback

Revision ID: 9ee7090d2edc
Revises: 002_user_personalization_schema
Create Date: 2026-10-04 21:10:28.111520

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ee7090d2edc'
down_revision: Union[str, Sequence[str], None] = '002_user_personalization_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user_feedback",
        sa.Column("session_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user_feedback", "session_id")
