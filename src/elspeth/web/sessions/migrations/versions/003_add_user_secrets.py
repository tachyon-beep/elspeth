"""Add user_secrets table.

Revision ID: 003
Revises: 002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add user_secrets table for Fernet-encrypted user-scoped secrets."""
    op.create_table(
        "user_secrets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("encrypted_value", sa.LargeBinary(), nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "user_id", name="uq_user_secret_name_user"),
    )
    op.create_index("ix_user_secrets_user_id", "user_secrets", ["user_id"])


def downgrade() -> None:
    """Drop user_secrets table."""
    op.drop_table("user_secrets")
