"""add chat session memory fields

Revision ID: 014
Revises: 013
Create Date: 2026-05-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("memory_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "chat_sessions",
        sa.Column(
            "memory_message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("memory_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "memory_updated_at")
    op.drop_column("chat_sessions", "memory_message_count")
    op.drop_column("chat_sessions", "memory_summary")
