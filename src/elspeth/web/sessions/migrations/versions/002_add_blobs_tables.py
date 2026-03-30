"""Add blobs and blob_run_links tables.

Revision ID: 002
Revises: 001
Create Date: 2026-03-30

Adds session-scoped blob management (REQ-API-01) with a normalized
join table for blob-to-run linkage.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add blobs and blob_run_links tables."""
    op.create_table(
        "blobs",
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
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "created_by IN ('user', 'assistant', 'pipeline')",
            name="ck_blobs_created_by",
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'pending', 'error')",
            name="ck_blobs_status",
        ),
    )
    op.create_index(op.f("ix_blobs_session_id"), "blobs", ["session_id"])

    op.create_table(
        "blob_run_links",
        sa.Column("blob_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["blob_id"], ["blobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("blob_id", "run_id", "direction", name="uq_blob_run_link"),
        sa.CheckConstraint(
            "direction IN ('input', 'output')",
            name="ck_blob_run_links_direction",
        ),
    )
    op.create_index("ix_blob_run_links_blob_id", "blob_run_links", ["blob_id"])
    op.create_index("ix_blob_run_links_run_id", "blob_run_links", ["run_id"])


def downgrade() -> None:
    """Drop blobs and blob_run_links tables."""
    op.drop_table("blob_run_links")
    op.drop_table("blobs")
