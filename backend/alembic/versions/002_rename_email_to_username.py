"""rename email to username

Revision ID: 002
Revises: 001
Create Date: 2026-05-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename the column
    op.alter_column('users', 'email', new_column_name='username')

    # Rename the index created by SQLAlchemy (index=True, unique=True)
    # The default name for this index is usually ix_users_email
    op.execute("ALTER INDEX ix_users_email RENAME TO ix_users_username")


def downgrade() -> None:
    # Revert the column name
    op.alter_column('users', 'username', new_column_name='email')

    # Revert the index name
    op.execute("ALTER INDEX ix_users_username RENAME TO ix_users_email")
