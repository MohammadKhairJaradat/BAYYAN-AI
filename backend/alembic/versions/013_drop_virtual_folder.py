"""drop unused virtual_folder column from documents

Revision ID: 013
Revises: 012
Create Date: 2026-05-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("documents", "virtual_folder")


def downgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("virtual_folder", sa.String(length=255), nullable=True),
    )
