"""add beneficiary tracking columns to deductions

Display/tracking only — `beneficiary` (self|spouse|child) and an optional
`beneficiary_name`. The tax engine pools deductions by category and ignores
these, so this is invisible to tax results. Both nullable → safe for existing
rows (no backfill needed).

Revision ID: 017
Revises: 016
Create Date: 2026-06-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _deduction_columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("deductions")}


def upgrade() -> None:
    columns = _deduction_columns()
    if "beneficiary" not in columns:
        op.add_column(
            "deductions",
            sa.Column("beneficiary", sa.String(length=20), nullable=True),
        )
    if "beneficiary_name" not in columns:
        op.add_column(
            "deductions",
            sa.Column("beneficiary_name", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    columns = _deduction_columns()
    if "beneficiary_name" in columns:
        op.drop_column("deductions", "beneficiary_name")
    if "beneficiary" in columns:
        op.drop_column("deductions", "beneficiary")
