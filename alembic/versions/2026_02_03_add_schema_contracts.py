"""add_schema_contracts

Add schema contract columns to runs, nodes, and validation_errors tables
for Phase 5 Unified Schema Contracts feature.

These columns enable full field mapping traceability in the audit trail:
- runs: Store run-level schema contract with field resolution and types
- nodes: Store per-node input requirements and output guarantees
- validation_errors: Store structured violation details for auditability

Revision ID: d8f3a7b2c1e9
Revises: c9d4e2f1a7b6
Create Date: 2026-02-03 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f3a7b2c1e9"
down_revision: str | Sequence[str] | None = "c9d4e2f1a7b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # runs table: schema contract columns
    op.add_column(
        "runs",
        sa.Column("schema_contract_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("schema_contract_hash", sa.String(16), nullable=True),
    )

    # nodes table: input/output contract columns
    op.add_column(
        "nodes",
        sa.Column("input_contract_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "nodes",
        sa.Column("output_contract_json", sa.Text(), nullable=True),
    )

    # validation_errors table: structured violation details
    op.add_column(
        "validation_errors",
        sa.Column("violation_type", sa.String(32), nullable=True),
    )
    op.add_column(
        "validation_errors",
        sa.Column("original_field_name", sa.String(256), nullable=True),
    )
    op.add_column(
        "validation_errors",
        sa.Column("normalized_field_name", sa.String(256), nullable=True),
    )
    op.add_column(
        "validation_errors",
        sa.Column("expected_type", sa.String(32), nullable=True),
    )
    op.add_column(
        "validation_errors",
        sa.Column("actual_type", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    # validation_errors table: remove structured violation details
    op.drop_column("validation_errors", "actual_type")
    op.drop_column("validation_errors", "expected_type")
    op.drop_column("validation_errors", "normalized_field_name")
    op.drop_column("validation_errors", "original_field_name")
    op.drop_column("validation_errors", "violation_type")

    # nodes table: remove input/output contract columns
    op.drop_column("nodes", "output_contract_json")
    op.drop_column("nodes", "input_contract_json")

    # runs table: remove schema contract columns
    op.drop_column("runs", "schema_contract_hash")
    op.drop_column("runs", "schema_contract_json")
