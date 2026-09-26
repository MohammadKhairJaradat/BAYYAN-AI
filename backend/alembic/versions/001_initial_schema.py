"""initial schema: users, tax_profiles, income_sources, deductions, documents, filing_history

Revision ID: 001
Revises:
Create Date: 2026-04-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), unique=True, index=True, nullable=False),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("is_active", sa.Boolean(), default=True),
    )

    # Documents (before deductions, since deductions references it)
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column(
            "upload_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("processing_status", sa.String(20), default="pending"),
        sa.Column("extracted_data", postgresql.JSONB(), nullable=True),
    )

    # Tax Profiles
    op.create_table(
        "tax_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("marital_status", sa.String(20), nullable=False),
        sa.Column("num_dependents", sa.Integer(), default=0),
        sa.Column("filing_status", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "tax_year", name="uq_user_tax_year"),
    )

    # Income Sources
    op.create_table(
        "income_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tax_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tax_profiles.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("employer_name", sa.String(255), nullable=True),
        sa.Column("description", sa.String(1024), nullable=True),
    )

    # Deductions
    op.create_table(
        "deductions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tax_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tax_profiles.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            index=True,
            nullable=True,
        ),
    )

    # Filing History
    op.create_table(
        "filing_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tax_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tax_profiles.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("total_income", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_deductions", sa.Numeric(12, 2), nullable=True),
        sa.Column("taxable_income", sa.Numeric(12, 2), nullable=True),
        sa.Column("tax_liability", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "filed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("filing_history")
    op.drop_table("deductions")
    op.drop_table("income_sources")
    op.drop_table("tax_profiles")
    op.drop_table("documents")
    op.drop_table("users")
