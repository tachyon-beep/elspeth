"""Add rows_succeeded/rows_quarantined to runs; add 'failed' to run_events CHECK.

These columns enable the WebSocket reconnect path to construct
complete CompletedData payloads (matching the live path) instead
of sending a degraded {rows_processed, rows_failed} subset.

The CHECK constraint update aligns the migration history with the
in-memory model (models.py) which already includes 'failed'.
Without this, databases upgraded via Alembic reject INSERT of
event_type='failed' while create_all() databases accept it.

Revision ID: 005
Revises: 004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | Sequence[str] | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add per-outcome row counts to runs; add 'failed' to event_type CHECK."""
    with op.batch_alter_table("runs") as batch_op:
        batch_op.add_column(sa.Column("rows_succeeded", sa.Integer(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("rows_quarantined", sa.Integer(), nullable=False, server_default=sa.text("0")))

    with op.batch_alter_table("run_events") as batch_op:
        batch_op.drop_constraint("ck_run_events_type", type_="check")
        batch_op.create_check_constraint(
            "ck_run_events_type",
            "event_type IN ('progress', 'error', 'completed', 'cancelled', 'failed')",
        )


def downgrade() -> None:
    """Remove per-outcome row counts; revert event_type CHECK."""
    with op.batch_alter_table("run_events") as batch_op:
        batch_op.drop_constraint("ck_run_events_type", type_="check")
        batch_op.create_check_constraint(
            "ck_run_events_type",
            "event_type IN ('progress', 'error', 'completed', 'cancelled')",
        )

    with op.batch_alter_table("runs") as batch_op:
        batch_op.drop_column("rows_quarantined")
        batch_op.drop_column("rows_succeeded")
