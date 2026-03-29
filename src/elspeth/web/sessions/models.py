"""SQLAlchemy Core table definitions for the session database.

Tables: sessions, chat_messages, composition_states, runs, run_events.
Schema creation via metadata.create_all(engine) on startup.

All tables live in a dedicated session database, separate from the
Landscape audit database.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON

metadata = MetaData()

sessions_table = Table(
    "sessions",
    metadata,
    Column("id", String, primary_key=True),
    Column("user_id", String, nullable=False, index=True),
    Column("auth_provider_type", String, nullable=False, default="local"),
    Column("title", String, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

chat_messages_table = Table(
    "chat_messages",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "session_id",
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("role", String, nullable=False),
    Column("content", Text, nullable=False),
    Column("tool_calls", JSON, nullable=True),
    Column("created_at", DateTime, nullable=False),
    CheckConstraint(
        "role IN ('user', 'assistant', 'system', 'tool')",
        name="ck_chat_messages_role",
    ),
)

composition_states_table = Table(
    "composition_states",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "session_id",
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("version", Integer, nullable=False),
    Column("source", JSON, nullable=True),
    Column("nodes", JSON, nullable=True),
    Column("edges", JSON, nullable=True),
    Column("outputs", JSON, nullable=True),
    Column("metadata_", JSON, nullable=True),
    Column("is_valid", Boolean, nullable=False, default=False),
    Column("validation_errors", JSON, nullable=True),
    Column("created_at", DateTime, nullable=False),
    Column(
        "derived_from_state_id",
        String,
        ForeignKey("composition_states.id"),
        nullable=True,
    ),
    UniqueConstraint("session_id", "version", name="uq_composition_state_version"),
)

runs_table = Table(
    "runs",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "session_id",
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "state_id",
        String,
        ForeignKey("composition_states.id"),
        nullable=False,
    ),
    Column("status", String, nullable=False),
    Column("started_at", DateTime, nullable=False),
    Column("finished_at", DateTime, nullable=True),
    Column("rows_processed", Integer, nullable=False, default=0),
    Column("rows_failed", Integer, nullable=False, default=0),
    Column("error", Text, nullable=True),
    Column("landscape_run_id", String, nullable=True),
    Column("pipeline_yaml", Text, nullable=True),
    CheckConstraint(
        "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
        name="ck_runs_status",
    ),
)

# Partial unique index: at most one active (pending/running) run per session.
# Enforces the one-active-run invariant at the database level, eliminating
# the TOCTOU race in the service-level check-and-insert.
Index(
    "uq_runs_one_active_per_session",
    runs_table.c.session_id,
    unique=True,
    sqlite_where=runs_table.c.status.in_(["pending", "running"]),
)

run_events_table = Table(
    "run_events",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "run_id",
        String,
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("timestamp", DateTime, nullable=False),
    Column("event_type", String, nullable=False),
    Column("data", JSON, nullable=False),
    CheckConstraint(
        "event_type IN ('progress', 'error', 'completed', 'cancelled')",
        name="ck_run_events_type",
    ),
)
