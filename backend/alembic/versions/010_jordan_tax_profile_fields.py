"""add Jordan tax profile fields

Revision ID: 010
Revises: 009
Create Date: 2026-05-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tax_profiles",
        sa.Column(
            "residency_status",
            sa.String(length=32),
            nullable=False,
            server_default="resident",
        ),
    )
    op.add_column(
        "tax_profiles",
        sa.Column(
            "claims_dependents_exemption",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tax_profiles",
        sa.Column(
            "claim_spouse_expense_exemption",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tax_profiles",
        sa.Column(
            "disability_exemption_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "income_sources",
        sa.Column(
            "tax_withheld",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )

    op.execute(
        """
        UPDATE tax_profiles
        SET
            claims_dependents_exemption =
                (marital_status = 'married' OR COALESCE(num_dependents, 0) > 0),
            claim_spouse_expense_exemption = (marital_status = 'married')
        """
    )


def downgrade() -> None:
    op.drop_column("income_sources", "tax_withheld")
    op.drop_column("tax_profiles", "disability_exemption_count")
    op.drop_column("tax_profiles", "claim_spouse_expense_exemption")
    op.drop_column("tax_profiles", "claims_dependents_exemption")
    op.drop_column("tax_profiles", "residency_status")
