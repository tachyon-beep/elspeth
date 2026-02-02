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
    # Use batch_alter_table for SQLite compatibility (recreates table)
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("schema_contract_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("schema_contract_hash", sa.String(16), nullable=True))

    # nodes table: input/output contract columns
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("input_contract_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("output_contract_json", sa.Text(), nullable=True))

    # validation_errors table: structured violation details
    with op.batch_alter_table("validation_errors", schema=None) as batch_op:
        batch_op.add_column(sa.Column("violation_type", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("original_field_name", sa.String(256), nullable=True))
        batch_op.add_column(sa.Column("normalized_field_name", sa.String(256), nullable=True))
        batch_op.add_column(sa.Column("expected_type", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("actual_type", sa.String(32), nullable=True))


def downgrade() -> None:
    # validation_errors table: remove structured violation details
    with op.batch_alter_table("validation_errors", schema=None) as batch_op:
        batch_op.drop_column("actual_type")
        batch_op.drop_column("expected_type")
        batch_op.drop_column("normalized_field_name")
        batch_op.drop_column("original_field_name")
        batch_op.drop_column("violation_type")

    # nodes table: remove input/output contract columns
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.drop_column("output_contract_json")
        batch_op.drop_column("input_contract_json")

    # runs table: remove schema contract columns
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("schema_contract_hash")
        batch_op.drop_column("schema_contract_json")
