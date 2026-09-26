"""Widen stored JOD money to three decimal places without reducing precision."""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None

_COLUMNS = {
    "income_sources": ("amount", "tax_withheld"),
    "deductions": ("amount",),
    "filing_history": ("total_income", "total_deductions", "taxable_income", "tax_liability"),
}


def upgrade() -> None:
    for table, columns in _COLUMNS.items():
        for column in columns:
            op.alter_column(
                table, column,
                existing_type=sa.Numeric(12, 2),
                type_=sa.Numeric(15, 3),
                existing_nullable=table == "filing_history",
            )


def downgrade() -> None:
    # Downgrading requires an explicit review of values with nonzero third
    # decimals; silently truncating user money would corrupt financial data.
    raise RuntimeError("Money precision cannot be downgraded without reviewing stored fils")
