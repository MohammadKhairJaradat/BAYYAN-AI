"""persist latest advisor reports

Revision ID: 012
Revises: 011
Create Date: 2026-05-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "advisor_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tax_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lang", sa.String(length=2), nullable=False),
        sa.Column(
            "report",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tax_profile_id"], ["tax_profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tax_profile_id", name="uq_advisor_reports_tax_profile_id"
        ),
    )
    op.create_index(
        "ix_advisor_reports_user_id", "advisor_reports", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_advisor_reports_user_id", table_name="advisor_reports")
    op.drop_table("advisor_reports")
