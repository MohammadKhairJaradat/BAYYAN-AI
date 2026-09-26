"""Version tax profiles and add append-only calculation snapshots."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tax_profiles", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_table(
        "calculation_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tax_profile_id", UUID(as_uuid=True), sa.ForeignKey("tax_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("ruleset_id", sa.String(64), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("input_snapshot", JSONB(), nullable=False),
        sa.Column("output_snapshot", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_calculation_runs_user_id", "calculation_runs", ["user_id"])
    op.create_index("ix_calculation_runs_tax_profile_id", "calculation_runs", ["tax_profile_id"])


def downgrade() -> None:
    # Saved reviews are user data. Never remove the table as a routine rollback.
    raise RuntimeError("Review and export calculation runs before downgrading migration 022")
