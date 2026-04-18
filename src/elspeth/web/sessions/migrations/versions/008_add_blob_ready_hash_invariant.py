"""Enforce ``ready`` blobs always carry a SHA-256 hex content_hash.

Revision ID: 008
Revises: 007
Create Date: 2026-04-17

Migration 002 created the ``blobs`` table without a cross-column
integrity invariant: ``content_hash`` was nullable for all statuses,
so a defective finalization path could persist a row with
``status='ready'`` and ``content_hash IS NULL``.  That violates the
audit contract (AD-5/AD-7 in
docs/plans/rc4.2-ux-remediation/2026-03-30-02-blob-manager-subplan.md)
— a ready blob is supposed to be verifiable against its stored
SHA-256, and a NULL hash silently turns "trust me" into the audit
trail's answer.

This migration enforces the invariant at the database layer so the
guarantee cannot be bypassed by future service-layer regressions or
direct SQL writes.  It pairs with a SHA-256 hex format check added in
``src/elspeth/web/blobs/service.py::_validate_finalize_hash`` which
refuses obviously-malformed hashes before they reach the DB.

The CHECK enforces both invariants the audit trail relies on:

1. ``content_hash IS NOT NULL`` for ``status='ready'`` rows — without
   this, ``read_blob_content`` cannot verify the bytes at all.
2. ``content_hash`` matches the canonical SHA-256 hex form (exactly 64
   lowercase hexadecimal characters).  Without this, a direct SQL or
   ORM write could persist ``content_hash='abc123'`` and leave a
   "ready" blob whose hash will never match any real bytes — every
   download would fail with ``BlobIntegrityError`` and the audit
   trail's "ready" claim would be a permanent lie.

The shape rule is the same one enforced at the write side by
``_validate_finalize_hash`` (``re.compile(r"^[a-f0-9]{64}$")``) and at
the storage layer by ``FilesystemPayloadStore``.  Keeping all three in
agreement is what makes the audit contract verifiable end-to-end.

Running this migration on a database that already contains a violating
row will fail — by design.  Operators must quarantine or repair any
such row before the constraint can be added.  The documented repair
procedure (with copy-pasteable SQL for both "transition to error" and
"back-fill from on-disk bytes" variants, plus diagnosis queries for
NULL and malformed hashes) lives in
``docs/runbooks/repair-blob-ready-hash.md``.

The CHECK clause is dialect-specific because portable SQL has no way
to express "matches a regular expression": SQLite supports ``GLOB``
with character classes and a length predicate; PostgreSQL provides the
POSIX regex operator ``~``.  Both encodings express the same shape
rule.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str | Sequence[str] | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _current_blobs_shape() -> sa.Table:
    """Shape of ``blobs`` BEFORE this migration, with every index/CHECK.

    IMMUTABLE SNAPSHOT — post-007, pre-008.  Do NOT update this when
    later migrations change the ``blobs`` table.  See migration 007's
    ``_current_runs_shape`` docstring for the full rationale: any
    index, CHECK, or FK NOT listed here is silently dropped during
    SQLite's table-copy rebuild, reopening whatever invariant the
    omitted constraint was enforcing.

    The non-obvious failure mode this snapshot closes is forward drift:
    a future migration that adds, say, a partial index
    ``WHERE status='ready'`` on ``blobs`` is safe under a pure-reflection
    rebuild (Alembic re-reads the live shape), but unsafe if 008's
    ``batch_alter_table`` is ever exercised again against a database
    carrying that later index.  Freezing the shape at the revision
    boundary makes the rebuild deterministic regardless of what has
    been applied since, and the matching drift-guard tests in
    ``TestMigration008PreservesBlobsShape`` catch any omission here
    before it reaches a production run.

    The ``downgrade()`` path deliberately does NOT reuse this snapshot:
    by the time 008 is being downgraded, the live ``blobs`` table
    already carries ``ck_blobs_ready_hash`` and passing a pre-008
    shape to ``copy_from`` would make Alembic's batch rebuild unable
    to locate the constraint to drop.  Matching migration 007's
    downgrade precedent, the downgrade uses reflection — correct
    because reflection reads the live post-008 shape at the moment
    the downgrade runs.
    """
    md = sa.MetaData()
    return sa.Table(
        "blobs",
        md,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("source_description", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="ready"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "created_by IN ('user', 'assistant', 'pipeline')",
            name="ck_blobs_created_by",
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'pending', 'error')",
            name="ck_blobs_status",
        ),
        sa.Index("ix_blobs_session_id", "session_id"),
    )


def _ready_hash_check_clause(dialect_name: str) -> str:
    """Return the dialect-specific CHECK clause for ``ck_blobs_ready_hash``.

    SQLite uses GLOB with a negated hex-character class plus an explicit
    length predicate — SQLite GLOB has no quantifier syntax for "exactly
    N of these," so the length is checked separately.  Negation in
    SQLite GLOB character classes is ``^`` (see the GLOB semantics
    documented at https://www.sqlite.org/lang_expr.html#like ;
    SQLite's ``patternCompare`` implementation uses ``^`` as the
    class-negation sentinel, diverging from POSIX shell glob which
    uses ``!``).  The POSIX-shell spelling ``[!a-f0-9]`` would treat
    ``!`` as a literal class member in SQLite and actually MATCH
    ``!`` in addition to hex chars — silently weakening the
    constraint without any syntax error to warn the operator.
    ``NOT GLOB '*[^a-f0-9]*'`` therefore matches strings containing
    only hex characters.  The same negated-class spelling is used by
    the diagnostic queries in
    ``docs/runbooks/repair-blob-ready-hash.md`` so operators see
    consistent syntax everywhere.

    PostgreSQL uses the POSIX regex operator ``~`` with the canonical
    SHA-256 hex anchor pattern, matching the write-side validator in
    ``service.py::_SHA256_HEX_PATTERN``.

    Anything else is rejected — silently emitting only the NULL guard
    on an unknown dialect would weaken the invariant the docstring
    promises and make the regression invisible until production. If a
    new dialect is supported it must explicitly declare its shape
    syntax here.
    """
    if dialect_name == "sqlite":
        return "status != 'ready' OR (content_hash IS NOT NULL AND length(content_hash) = 64 AND content_hash NOT GLOB '*[^a-f0-9]*')"
    if dialect_name in {"postgresql", "postgres"}:
        return "status != 'ready' OR (content_hash IS NOT NULL AND content_hash ~ '^[a-f0-9]{64}$')"
    raise NotImplementedError(
        f"ck_blobs_ready_hash has no shape clause defined for dialect "
        f"{dialect_name!r}.  Add an explicit branch to "
        f"_ready_hash_check_clause before running 008 on this backend."
    )


def upgrade() -> None:
    """Add CHECK ensuring status='ready' implies a SHA-256 hex content_hash."""
    bind = op.get_bind()
    clause = _ready_hash_check_clause(bind.dialect.name)
    with op.batch_alter_table("blobs", copy_from=_current_blobs_shape()) as batch_op:
        batch_op.create_check_constraint(
            "ck_blobs_ready_hash",
            clause,
        )


def downgrade() -> None:
    """Drop the ready⇒valid-hash invariant.

    No ``copy_from`` here: Alembic reflects the live post-008 shape
    (including ``ck_blobs_ready_hash``) and the rebuild drops the
    constraint.  See ``_current_blobs_shape`` docstring for the full
    rationale — passing a pre-008 shape would leave Alembic unable to
    locate the constraint we are trying to drop.
    """
    with op.batch_alter_table("blobs") as batch_op:
        batch_op.drop_constraint("ck_blobs_ready_hash", type_="check")
