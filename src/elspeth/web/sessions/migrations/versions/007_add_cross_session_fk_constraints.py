"""Add composite FKs enforcing same-session ownership on composition_states references.

Revision ID: 007
Revises: 006
Create Date: 2026-04-17

chat_messages.composition_state_id and runs.state_id were single-column
FKs to composition_states.id, which permitted cross-session references:
a message/run in session B could point at a state owned by session A.

This migration:

1. Scans for existing cross-session violations. Any hit is a Tier 1
   integrity failure — we refuse to apply the FK over corrupt data.
2. Adds a composite ``UniqueConstraint(id, session_id)`` on
   composition_states so engines accept ``(id, session_id)`` as an FK
   target.
3. Drops the old single-column FKs and replaces them with composite
   FKs so the DB enforces same-session ownership.

Dialect handling
----------------

SQLite and non-SQLite use different paths because ``batch_alter_table``
only performs a table-copy rebuild on SQLite. On PostgreSQL/MySQL it
issues direct DDL that runs against *live* constraint names, so the
name the old FK was created with matters.

* Revision 004 named the chat_messages.composition_state_id FK
  ``fk_chat_messages_composition_state`` (no ``_id`` suffix).
* Revision 001 left the runs.state_id FK unnamed, so on
  PostgreSQL/MySQL the backend assigns a generated name (e.g.
  ``runs_state_id_fkey`` on Postgres).

**SQLite path**: ``batch_alter_table`` with ``copy_from`` — names are
only used to identify which constraint in the ``copy_from`` shape to
exclude from the new table, and every index in ``copy_from`` is
preserved. Indexes that are NOT listed in the shape vanish, so the
shape must enumerate every index that revisions 001-006 created on
these tables (notably ``uq_runs_one_active_per_session``, the partial
unique index that enforces at-most-one-active-run-per-session).

**Non-SQLite path**: reflect the live FK name (since revision 001 did
not name the runs FK), then run direct DDL. Indexes are unaffected
because the table is not rebuilt.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str | Sequence[str] | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The live FK name revision 004 assigned. Used both in the SQLite
# copy_from shape and in the non-SQLite drop_constraint call so the two
# paths stay aligned — if revision 004 is ever edited to change this
# name, both paths break the same way.
_CHAT_MESSAGES_STATE_FK_NAME = "fk_chat_messages_composition_state"

# Revision 001 created the runs.state_id FK without an explicit name.
# On non-SQLite we reflect the live name at migration time (see
# ``_reflect_single_column_fk``). On SQLite this placeholder exists only
# so ``batch_op.drop_constraint`` can identify the constraint inside the
# copy_from shape to exclude — SQLite does not persist FK names.
_RUNS_STATE_FK_SQLITE_PLACEHOLDER = "_runs_state_id_pre007"


def _current_chat_messages_shape() -> sa.Table:
    """Shape of chat_messages BEFORE this migration, with every index.

    IMMUTABLE SNAPSHOT — post-006, pre-007. Do NOT update this when
    later migrations add or change chat_messages columns. Alembic's
    ``copy_from`` uses this shape to rebuild the table on SQLite; any
    index NOT listed here vanishes during the rebuild, and any column
    not listed here is dropped. If a future migration needs a current
    shape, it must define its OWN snapshot captured at its own
    revision boundary.

    The FK name MUST match what revision 004 assigned, because on
    non-SQLite ``drop_constraint`` runs as live DDL against that name.
    """
    md = sa.MetaData()
    return sa.Table(
        "chat_messages",
        md,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("composition_state_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="CASCADE",
            name="fk_chat_messages_session_id",
        ),
        sa.ForeignKeyConstraint(
            ["composition_state_id"],
            ["composition_states.id"],
            name=_CHAT_MESSAGES_STATE_FK_NAME,
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="ck_chat_messages_role",
        ),
        sa.Index("ix_chat_messages_session_id", "session_id"),
    )


def _current_runs_shape() -> sa.Table:
    """Shape of runs BEFORE this migration, with every index.

    IMMUTABLE SNAPSHOT — post-006, pre-007. See the docstring on
    ``_current_chat_messages_shape`` above for why this must never be
    updated when later migrations change the ``runs`` table. Each
    migration that uses ``copy_from`` needs its own revision-pinned
    snapshot; sharing this one with a future migration is a data-loss
    bug waiting to happen.

    Critically, ``uq_runs_one_active_per_session`` (the partial unique
    index that enforces at-most-one-active-run-per-session) is
    declared here so SQLite's batch rebuild reproduces it with the
    WHERE clause intact. Omitting it, or losing the ``sqlite_where``
    predicate, reopens the TOCTOU race that ``create_run()`` relies on
    the index to close.
    """
    md = sa.MetaData()
    return sa.Table(
        "runs",
        md,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("state_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("rows_processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rows_succeeded", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rows_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rows_quarantined", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("landscape_run_id", sa.String(), nullable=True),
        sa.Column("pipeline_yaml", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="CASCADE",
            name="fk_runs_session_id",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["composition_states.id"],
            name=_RUNS_STATE_FK_SQLITE_PLACEHOLDER,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_runs_status",
        ),
        sa.Index("ix_runs_session_id", "session_id"),
        sa.Index(
            "uq_runs_one_active_per_session",
            "session_id",
            unique=True,
            sqlite_where=sa.text("status IN ('pending', 'running')"),
        ),
    )


def _reflect_single_column_fk(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
) -> str:
    """Return the live FK name covering exactly ``[column_name]``.

    Used on non-SQLite because revision 001 left ``runs.state_id``
    unnamed — the actual name is backend-generated and only discoverable
    at runtime. Raises if the FK is not found or (on PostgreSQL/MySQL)
    reports no name, which would indicate a schema drift we should not
    silently paper over.
    """
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys(table_name):
        if fk["constrained_columns"] == [column_name]:
            name = fk["name"]
            if not name:
                raise RuntimeError(
                    f"Cannot drop FK on {table_name}.{column_name}: "
                    f"backend reported an unnamed FK. PostgreSQL and "
                    f"MySQL always generate names; this indicates schema "
                    f"drift or an unsupported dialect."
                )
            return name
    raise RuntimeError(
        f"Migration 007 cannot locate the single-column FK on "
        f"{table_name}.{column_name}. Expected a pre-007 FK to "
        f"composition_states.id; none was found. Remediate the schema "
        f"manually before re-running migrations."
    )


def upgrade() -> None:
    bind = op.get_bind()

    # --- Tier 1 integrity scan ---
    # The composite FK enforces on INSERT/UPDATE, not on existing rows.
    # Surface any pre-existing cross-session references so an operator
    # remediates them — silently applying the FK over corrupt data would
    # leave orphaned lineage invisible to the new constraint.
    chat_orphans = bind.execute(
        sa.text(
            """
            SELECT m.id AS message_id,
                   m.session_id AS message_session_id,
                   m.composition_state_id,
                   s.session_id AS state_session_id
            FROM chat_messages m
            JOIN composition_states s ON s.id = m.composition_state_id
            WHERE m.composition_state_id IS NOT NULL
              AND m.session_id <> s.session_id
            """
        )
    ).fetchall()
    if chat_orphans:
        raise RuntimeError(
            f"Migration 007 blocked: {len(chat_orphans)} chat_messages rows "
            "reference a composition_state from a different session. "
            "Tier 1 integrity failure — cannot apply composite FK over "
            f"corrupt data. Example row: {chat_orphans[0]!r}. Remediate "
            "manually before re-running migrations."
        )

    run_orphans = bind.execute(
        sa.text(
            """
            SELECT r.id AS run_id,
                   r.session_id AS run_session_id,
                   r.state_id,
                   s.session_id AS state_session_id
            FROM runs r
            JOIN composition_states s ON s.id = r.state_id
            WHERE r.session_id <> s.session_id
            """
        )
    ).fetchall()
    if run_orphans:
        raise RuntimeError(
            f"Migration 007 blocked: {len(run_orphans)} runs rows "
            "reference a composition_state from a different session. "
            "Tier 1 integrity failure — cannot apply composite FK over "
            f"corrupt data. Example row: {run_orphans[0]!r}. Remediate "
            "manually before re-running migrations."
        )

    # --- Schema changes ---

    # composite uniqueness target — same DDL on every dialect.
    with op.batch_alter_table("composition_states") as batch_op:
        batch_op.create_unique_constraint(
            "uq_composition_state_id_session",
            ["id", "session_id"],
        )

    if bind.dialect.name == "sqlite":
        # SQLite: batch rebuild via copy_from. The shape functions
        # carry every index and the FK names we drop against — names
        # here are internal identifiers used to pick entries out of
        # the copy_from shape, not live DDL targets.
        with op.batch_alter_table("chat_messages", copy_from=_current_chat_messages_shape()) as batch_op:
            batch_op.drop_constraint(_CHAT_MESSAGES_STATE_FK_NAME, type_="foreignkey")
            batch_op.create_foreign_key(
                "fk_chat_messages_composition_state_session",
                "composition_states",
                ["composition_state_id", "session_id"],
                ["id", "session_id"],
            )

        with op.batch_alter_table("runs", copy_from=_current_runs_shape()) as batch_op:
            batch_op.drop_constraint(_RUNS_STATE_FK_SQLITE_PLACEHOLDER, type_="foreignkey")
            batch_op.create_foreign_key(
                "fk_runs_state_session",
                "composition_states",
                ["state_id", "session_id"],
                ["id", "session_id"],
            )
        return

    # Non-SQLite: direct DDL using reflected FK names. The table is
    # not rebuilt, so indexes carry through untouched.
    op.drop_constraint(
        _CHAT_MESSAGES_STATE_FK_NAME,
        "chat_messages",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_chat_messages_composition_state_session",
        "chat_messages",
        "composition_states",
        ["composition_state_id", "session_id"],
        ["id", "session_id"],
    )

    runs_state_fk_name = _reflect_single_column_fk(bind, "runs", "state_id")
    op.drop_constraint(runs_state_fk_name, "runs", type_="foreignkey")
    op.create_foreign_key(
        "fk_runs_state_session",
        "runs",
        "composition_states",
        ["state_id", "session_id"],
        ["id", "session_id"],
    )


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch_op:
        batch_op.drop_constraint("fk_runs_state_session", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_runs_state_id",
            "composition_states",
            ["state_id"],
            ["id"],
        )

    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_constraint("fk_chat_messages_composition_state_session", type_="foreignkey")
        batch_op.create_foreign_key(
            _CHAT_MESSAGES_STATE_FK_NAME,
            "composition_states",
            ["composition_state_id"],
            ["id"],
        )

    with op.batch_alter_table("composition_states") as batch_op:
        batch_op.drop_constraint("uq_composition_state_id_session", type_="unique")
