"""Add rows_routed to runs so web execution can round-trip routed counts.

Revision ID: 009
Revises: 008
Create Date: 2026-04-22

The orchestrator reports routed rows as a distinct terminal bucket, but
the sessions ``runs`` table only persisted processed/succeeded/failed/
quarantined counts. That made routed terminal runs impossible to
represent faithfully in ``RunStatusResponse`` / ``RunResultsResponse``:
either the web layer dropped the routed rows entirely or the completed
payload failed its row-decomposition invariant.

This migration adds a dedicated ``rows_routed`` integer column with a
zero default so existing rows remain readable and new terminal states can
round-trip the same counters the engine produced.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: str | Sequence[str] | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add rows_routed to the runs table."""
    with op.batch_alter_table("runs") as batch_op:
        batch_op.add_column(sa.Column("rows_routed", sa.Integer(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    """Remove rows_routed from the runs table."""
    with op.batch_alter_table("runs") as batch_op:
        batch_op.drop_column("rows_routed")
