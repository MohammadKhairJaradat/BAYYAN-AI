"""repair chat session memory columns

Revision ID: 015
Revises: 014
Create Date: 2026-05-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _chat_session_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("chat_sessions")}


def upgrade() -> None:
    columns = _chat_session_columns()

    if "memory_summary" not in columns:
        op.add_column(
            "chat_sessions",
            sa.Column("memory_summary", sa.Text(), nullable=True),
        )

    if "memory_message_count" not in columns:
        op.add_column(
            "chat_sessions",
            sa.Column(
                "memory_message_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    if "memory_updated_at" not in columns:
        op.add_column(
            "chat_sessions",
            sa.Column("memory_updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    # No-op: revision 014 is the canonical owner of these columns. This repair
    # migration only brings drifted dev DBs back to the 014 schema shape.
    pass
