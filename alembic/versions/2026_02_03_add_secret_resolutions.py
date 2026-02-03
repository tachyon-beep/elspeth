"""add_secret_resolutions

Add secret_resolutions table for audit trail of secrets loaded from
Azure Key Vault during pipeline startup.

This enables auditors to answer: "Which Key Vault did this secret come from?"
without exposing actual secret values (stores HMAC fingerprint only).

P2-10: Key Vault secrets configuration feature.

Revision ID: e9f4a8c3d2b1
Revises: d8f3a7b2c1e9
Create Date: 2026-02-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9f4a8c3d2b1"
down_revision: str | Sequence[str] | None = "d8f3a7b2c1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "secret_resolutions",
        sa.Column("resolution_id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("runs.run_id"), nullable=False, index=True),
        sa.Column("timestamp", sa.Float(), nullable=False),
        sa.Column("env_var_name", sa.String(256), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("vault_url", sa.Text(), nullable=True),
        sa.Column("secret_name", sa.String(256), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("resolution_latency_ms", sa.Float(), nullable=True),
    )
    op.create_index("ix_secret_resolutions_run", "secret_resolutions", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_secret_resolutions_run", table_name="secret_resolutions")
    op.drop_table("secret_resolutions")
