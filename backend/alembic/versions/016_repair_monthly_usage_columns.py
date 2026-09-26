"""repair monthly usage counter columns

Revision ID: 016
Revises: 015
Create Date: 2026-05-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _monthly_usage_columns() -> set[str]:
    return {column["name"] for column in _inspector().get_columns("monthly_usage")}


def _create_monthly_usage_table() -> None:
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


def upgrade() -> None:
    inspector = _inspector()
    if "monthly_usage" not in set(inspector.get_table_names()):
        _create_monthly_usage_table()
        return

    columns = _monthly_usage_columns()

    if "message_count" not in columns:
        op.add_column(
            "monthly_usage",
            sa.Column(
                "message_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    if "doc_count" not in columns:
        op.add_column(
            "monthly_usage",
            sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
        )
    else:
        op.execute("UPDATE monthly_usage SET doc_count = 0 WHERE doc_count IS NULL")
        op.alter_column(
            "monthly_usage",
            "doc_count",
            existing_type=sa.Integer(),
            nullable=False,
            server_default="0",
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("monthly_usage")}
    if "ix_monthly_usage_user_id" not in existing_indexes:
        op.create_index("ix_monthly_usage_user_id", "monthly_usage", ["user_id"])

    existing_uniques = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("monthly_usage")
    }
    if "uq_monthly_usage_user_month" not in existing_uniques:
        op.create_unique_constraint(
            "uq_monthly_usage_user_month",
            "monthly_usage",
            ["user_id", "usage_month"],
        )


def downgrade() -> None:
    # No-op: revision 009 is the canonical owner of monthly_usage. This repair
    # migration only brings drifted dev DBs back to the 009 schema shape.
    pass
