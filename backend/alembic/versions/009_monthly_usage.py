"""add monthly usage counters

Revision ID: 009
Revises: 008
Create Date: 2026-05-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "monthly_usage" in existing_tables:
        existing_indexes = {
            index["name"]
            for index in inspector.get_indexes("monthly_usage")
        }
        if "ix_monthly_usage_user_id" not in existing_indexes:
            op.create_index("ix_monthly_usage_user_id", "monthly_usage", ["user_id"])
        return

    op.create_table(
        "monthly_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("usage_month", sa.Date(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id",
            "usage_month",
            name="uq_monthly_usage_user_month",
        ),
    )
    op.create_index("ix_monthly_usage_user_id", "monthly_usage", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "monthly_usage" in set(inspector.get_table_names()):
        existing_indexes = {
            index["name"]
            for index in inspector.get_indexes("monthly_usage")
        }
        if "ix_monthly_usage_user_id" in existing_indexes:
            op.drop_index("ix_monthly_usage_user_id", table_name="monthly_usage")
        op.drop_table("monthly_usage")
