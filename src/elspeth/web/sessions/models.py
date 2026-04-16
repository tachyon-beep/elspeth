"""SQLAlchemy Core table definitions for the session database.

Tables: sessions, chat_messages, composition_states, runs, run_events,
blobs, blob_run_links.

Schema evolution via Alembic migrations (sessions/migrations/).

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
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
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
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column(
        "forked_from_session_id",
        String,
        ForeignKey("sessions.id"),
        nullable=True,
    ),
    Column("forked_from_message_id", String, nullable=True),
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
    Column("created_at", DateTime(timezone=True), nullable=False),
    # Composite FK forces same-session ownership: a message in session B
    # cannot reference a composition state owned by session A. When
    # composition_state_id is NULL, standard SQL partial-null semantics
    # skip FK enforcement, which is the intended behavior.
    Column("composition_state_id", String, nullable=True),
    ForeignKeyConstraint(
        ["composition_state_id", "session_id"],
        ["composition_states.id", "composition_states.session_id"],
        name="fk_chat_messages_composition_state_session",
    ),
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
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column(
        "derived_from_state_id",
        String,
        ForeignKey("composition_states.id"),
        nullable=True,
    ),
    UniqueConstraint("session_id", "version", name="uq_composition_state_version"),
    # Composite uniqueness target for composite FKs on chat_messages /
    # runs. The primary key already makes `id` unique on its own; this
    # constraint exists solely so SQL engines (including Postgres) will
    # accept (id, session_id) as an FK reference.
    UniqueConstraint("id", "session_id", name="uq_composition_state_id_session"),
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
    # Composite FK forces same-session ownership: a run in session B
    # cannot reference a composition state owned by session A. state_id
    # is NOT NULL so no partial-null concerns.
    Column("state_id", String, nullable=False),
    Column("status", String, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("rows_processed", Integer, nullable=False, default=0),
    Column("rows_succeeded", Integer, nullable=False, default=0),
    Column("rows_failed", Integer, nullable=False, default=0),
    Column("rows_quarantined", Integer, nullable=False, default=0),
    Column("error", Text, nullable=True),
    Column("landscape_run_id", String, nullable=True),
    Column("pipeline_yaml", Text, nullable=True),
    ForeignKeyConstraint(
        ["state_id", "session_id"],
        ["composition_states.id", "composition_states.session_id"],
        name="fk_runs_state_session",
    ),
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

blobs_table = Table(
    "blobs",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "session_id",
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("filename", String, nullable=False),
    Column("mime_type", String, nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("content_hash", String, nullable=True),
    Column("storage_path", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("created_by", String, nullable=False),
    Column("source_description", String, nullable=True),
    Column("status", String, nullable=False, server_default="ready"),
    CheckConstraint(
        "created_by IN ('user', 'assistant', 'pipeline')",
        name="ck_blobs_created_by",
    ),
    CheckConstraint(
        "status IN ('ready', 'pending', 'error')",
        name="ck_blobs_status",
    ),
)

blob_run_links_table = Table(
    "blob_run_links",
    metadata,
    Column(
        "blob_id",
        String,
        ForeignKey("blobs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "run_id",
        String,
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("direction", String, nullable=False),
    UniqueConstraint("blob_id", "run_id", "direction", name="uq_blob_run_link"),
    CheckConstraint(
        "direction IN ('input', 'output')",
        name="ck_blob_run_links_direction",
    ),
)
Index("ix_blob_run_links_blob_id", blob_run_links_table.c.blob_id)
Index("ix_blob_run_links_run_id", blob_run_links_table.c.run_id)

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
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("event_type", String, nullable=False),
    Column("data", JSON, nullable=False),
    CheckConstraint(
        "event_type IN ('progress', 'error', 'completed', 'cancelled', 'failed')",
        name="ck_run_events_type",
    ),
)

user_secrets_table = Table(
    "user_secrets",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("user_id", String, nullable=False),
    Column("auth_provider_type", String, nullable=False),
    Column("encrypted_value", LargeBinary, nullable=False),
    Column("salt", LargeBinary, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("name", "user_id", "auth_provider_type", name="uq_user_secret_name_user_provider"),
)
Index("ix_user_secrets_user_provider", user_secrets_table.c.user_id, user_secrets_table.c.auth_provider_type)
