"""Baseline schema — sessions, chat_messages, composition_states, runs, run_events.

Revision ID: 001
Revises: None
Create Date: 2026-03-30

This is the initial migration capturing the existing sessions.db schema.

Schema-shape detection:

- **Empty DB** → create the full baseline (fresh install).
- **Exact legacy five-table schema** → stamp as applied (DB created by
  the pre-Alembic ``metadata.create_all()`` path).
- **Anything else** → refuse to stamp. A partial schema, a newer
  pre-Alembic schema (already contains ``blobs``/``user_secrets``/etc.),
  or an unknown database would silently stamp 001 and fail at 002+,
  potentially leaving a half-migrated state. Tier 1 discipline: crash,
  don't guess.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Exact table set this revision creates. Databases whose user tables match
# this set (no more, no less) are safe to stamp as 001 without DDL.
_BASELINE_TABLES: frozenset[str] = frozenset({"sessions", "chat_messages", "composition_states", "runs", "run_events"})

# Alembic creates alembic_version before calling upgrade(); it is not part
# of the schema shape we compare against.
_ALEMBIC_INTERNAL: frozenset[str] = frozenset({"alembic_version"})


def _user_tables() -> frozenset[str]:
    """Existing user-defined tables, excluding Alembic's own bookkeeping."""
    bind = op.get_bind()
    all_tables = set(sa.inspect(bind).get_table_names())
    return frozenset(all_tables - _ALEMBIC_INTERNAL)


def upgrade() -> None:
    """Create baseline tables, stamp, or crash based on exact shape."""
    existing = _user_tables()

    if existing == _BASELINE_TABLES:
        # DB already at exact baseline shape (pre-Alembic create_all() path).
        # Stamp without running DDL.
        return

    if existing:
        raise RuntimeError(
            "Session database refuses to stamp revision 001: existing tables "
            f"{sorted(existing)!r} do not match the exact baseline set "
            f"{sorted(_BASELINE_TABLES)!r}. Remediate the schema manually "
            "(inspect, back up, reconcile) before re-running migrations. "
            "Silent stamping would cause later revisions to fail or leave "
            "the database half-migrated."
        )

    _create_baseline_tables()


def _create_baseline_tables() -> None:
    """Create the five baseline tables and their indexes."""
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("auth_provider_type", sa.String(), nullable=False, server_default="local"),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="ck_chat_messages_role",
        ),
    )
    op.create_index(op.f("ix_chat_messages_session_id"), "chat_messages", ["session_id"])

    op.create_table(
        "composition_states",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=True),
        sa.Column("nodes", sa.JSON(), nullable=True),
        sa.Column("edges", sa.JSON(), nullable=True),
        sa.Column("outputs", sa.JSON(), nullable=True),
        sa.Column("metadata_", sa.JSON(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("validation_errors", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("derived_from_state_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["derived_from_state_id"], ["composition_states.id"]),
        sa.UniqueConstraint("session_id", "version", name="uq_composition_state_version"),
    )
    op.create_index(op.f("ix_composition_states_session_id"), "composition_states", ["session_id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("state_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("rows_processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rows_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("landscape_run_id", sa.String(), nullable=True),
        sa.Column("pipeline_yaml", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["state_id"], ["composition_states.id"]),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_runs_status",
        ),
    )
    op.create_index(op.f("ix_runs_session_id"), "runs", ["session_id"])
    # Partial unique index: at most one active run per session
    op.execute("CREATE UNIQUE INDEX uq_runs_one_active_per_session ON runs (session_id) WHERE status IN ('pending', 'running')")

    op.create_table(
        "run_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "event_type IN ('progress', 'error', 'completed', 'cancelled')",
            name="ck_run_events_type",
        ),
    )
    op.create_index(op.f("ix_run_events_run_id"), "run_events", ["run_id"])


def downgrade() -> None:
    """Drop all baseline tables."""
    op.drop_table("run_events")
    op.drop_table("runs")
    op.drop_table("composition_states")
    op.drop_table("chat_messages")
    op.drop_table("sessions")
