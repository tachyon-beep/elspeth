"""Add auth_provider_type to user_secrets for provider-scoped isolation.

The rest of the web layer treats (user_id, auth_provider_type) as the
ownership boundary (sessions, execution, blobs).  user_secrets was keyed
only by user_id, so secrets could collide or leak across auth-provider
namespaces when different providers produce the same user_id string.

This migration adds the column, widens the unique constraint to
(name, user_id, auth_provider_type), and replaces the user_id-only
index with a composite index.

Existing rows are backfilled with the deployment's configured
auth_provider (passed via Alembic config attributes from run_migrations).
This preserves secret visibility: an OIDC deployment stamps existing
rows as "oidc", so reads filtering by "oidc" continue to find them.

Revision ID: 006
Revises: 005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | Sequence[str] | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add auth_provider_type column and widen uniqueness to include provider."""
    # Read the deployment's auth provider from the Alembic config attributes
    # set by run_migrations(). Falls back to "local" for CLI-driven migrations
    # or test environments where no config is available.
    context = op.get_context()
    assert context.config is not None, "Alembic MigrationContext has no Config — cannot read attributes"
    auth_provider = context.config.attributes.get("auth_provider", "local")

    # SQLite requires batch mode to alter constraints on existing tables.
    with op.batch_alter_table("user_secrets") as batch_op:
        batch_op.add_column(sa.Column("auth_provider_type", sa.String(), nullable=False, server_default=auth_provider))
        batch_op.drop_constraint("uq_user_secret_name_user", type_="unique")
        batch_op.create_unique_constraint("uq_user_secret_name_user_provider", ["name", "user_id", "auth_provider_type"])
        batch_op.drop_index("ix_user_secrets_user_id")
        batch_op.create_index("ix_user_secrets_user_provider", ["user_id", "auth_provider_type"])


def downgrade() -> None:
    """Remove auth_provider_type column and restore original constraints."""
    with op.batch_alter_table("user_secrets") as batch_op:
        batch_op.drop_index("ix_user_secrets_user_provider")
        batch_op.drop_constraint("uq_user_secret_name_user_provider", type_="unique")
        batch_op.create_unique_constraint("uq_user_secret_name_user", ["name", "user_id"])
        batch_op.create_index("ix_user_secrets_user_id", ["user_id"])
        batch_op.drop_column("auth_provider_type")
