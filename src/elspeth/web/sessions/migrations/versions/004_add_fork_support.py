"""Add fork support — forked_from fields on sessions, composition_state_id on chat_messages.

Revision ID: 004
Revises: 003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | Sequence[str] | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add fork provenance columns to sessions and chat_messages."""
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("forked_from_session_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("forked_from_message_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_sessions_forked_from",
            "sessions",
            ["forked_from_session_id"],
            ["id"],
        )

    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(sa.Column("composition_state_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_chat_messages_composition_state",
            "composition_states",
            ["composition_state_id"],
            ["id"],
        )


def downgrade() -> None:
    """Remove fork support columns."""
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_constraint("fk_chat_messages_composition_state", type_="foreignkey")
        batch_op.drop_column("composition_state_id")

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_constraint("fk_sessions_forked_from", type_="foreignkey")
        batch_op.drop_column("forked_from_message_id")
        batch_op.drop_column("forked_from_session_id")
