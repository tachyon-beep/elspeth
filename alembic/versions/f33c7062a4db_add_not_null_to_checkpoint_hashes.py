"""add_not_null_to_checkpoint_hashes

Revision ID: f33c7062a4db
Revises:
Create Date: 2026-01-25 21:39:08.223745

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f33c7062a4db"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add NOT NULL constraints to checkpoint topology hash fields.

    These fields are audit-critical for topology validation (Bug #1 fix).
    They should NEVER be NULL as they validate checkpoint compatibility.
    """
    # Use batch_alter_table for SQLite compatibility (recreates table)
    with op.batch_alter_table("checkpoints", schema=None) as batch_op:
        batch_op.alter_column("upstream_topology_hash", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("checkpoint_node_config_hash", existing_type=sa.String(length=64), nullable=False)


def downgrade() -> None:
    """Remove NOT NULL constraints from checkpoint topology hash fields."""
    with op.batch_alter_table("checkpoints", schema=None) as batch_op:
        batch_op.alter_column("checkpoint_node_config_hash", existing_type=sa.String(length=64), nullable=True)
        batch_op.alter_column("upstream_topology_hash", existing_type=sa.String(length=64), nullable=True)
