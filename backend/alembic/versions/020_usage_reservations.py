"""Idempotent, operation-scoped AI usage reservations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_reservations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usage_month", sa.Date(), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "operation", "idempotency_key", name="uq_usage_reservation_key"),
    )
    op.create_index("ix_usage_reservations_user_id", "usage_reservations", ["user_id"])
    op.create_index("ix_usage_reservations_usage_month", "usage_reservations", ["usage_month"])


def downgrade() -> None:
    op.drop_index("ix_usage_reservations_usage_month", table_name="usage_reservations")
    op.drop_index("ix_usage_reservations_user_id", table_name="usage_reservations")
    op.drop_table("usage_reservations")
