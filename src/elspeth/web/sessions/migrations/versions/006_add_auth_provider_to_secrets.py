"""Add auth_provider_type to user_secrets for provider-scoped isolation.

The rest of the web layer treats (user_id, auth_provider_type) as the
ownership boundary (sessions, execution, blobs).  user_secrets was keyed
only by user_id, so secrets could collide or leak across auth-provider
namespaces when different providers produce the same user_id string.

This migration adds the column, widens the unique constraint to
(name, user_id, auth_provider_type), and replaces the user_id-only
index with a composite index.

Legacy rows (pre-dating provider scoping) never asserted an
auth_provider_type.  Backfilling them with the deployment's current
auth_provider value would fabricate ownership (per the CLAUDE.md
fabrication decision test): if an installation changed provider
between the legacy rows being written and this migration running, the
backfill would silently transfer secrets into the wrong auth namespace.
Any collision on user_id across providers would then leak secrets
across accounts.

The migration therefore refuses to fabricate.  When legacy rows exist,
it raises with a clear remediation path: delete the rows (user-entered
secrets can be recreated via POST /api/secrets) or map them to the
correct provider manually before re-running.  With no legacy rows the
column is added without a server-default; every INSERT already provides
auth_provider_type explicitly via UserSecretStore.set_secret.

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
    """Add auth_provider_type; refuse to fabricate on legacy rows."""
    bind = op.get_bind()
    legacy = bind.execute(sa.text("SELECT COUNT(*) FROM user_secrets")).scalar_one()
    if legacy:
        raise RuntimeError(
            f"Cannot migrate {legacy} pre-existing user_secrets row(s) to revision "
            f"006: these rows have no auth_provider_type, and assigning one from "
            f"current deployment config would fabricate ownership (see CLAUDE.md's "
            f"fabrication decision test). Remediate before re-running:\n"
            f"  (a) delete them (`DELETE FROM user_secrets;`) — secrets are "
            f"user-entered and can be recreated via POST /api/secrets; or\n"
            f"  (b) assign each row to the correct provider manually "
            f"(UPDATE user_secrets SET auth_provider_type = ... WHERE ...) "
            f"before re-running migrations."
        )

    # SQLite requires batch mode to alter constraints on existing tables.
    with op.batch_alter_table("user_secrets") as batch_op:
        batch_op.add_column(sa.Column("auth_provider_type", sa.String(), nullable=False))
        batch_op.drop_constraint("uq_user_secret_name_user", type_="unique")
        batch_op.create_unique_constraint(
            "uq_user_secret_name_user_provider",
            ["name", "user_id", "auth_provider_type"],
        )
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
