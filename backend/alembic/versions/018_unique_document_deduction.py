"""Enforce the current one-document-to-one-deduction model.

Existing duplicates require a human review: their tax impact cannot safely be
resolved by keeping an arbitrary row.
"""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(sa.text("""
        SELECT document_id, COUNT(*) AS total
        FROM deductions WHERE document_id IS NOT NULL
        GROUP BY document_id HAVING COUNT(*) > 1
        LIMIT 5
    """)).all()
    if duplicates:
        ids = ", ".join(str(row.document_id) for row in duplicates)
        raise RuntimeError(
            "Review duplicate document-linked deductions before migration 018: " + ids
        )
    op.create_unique_constraint("uq_deductions_document_id", "deductions", ["document_id"])


def downgrade() -> None:
    op.drop_constraint("uq_deductions_document_id", "deductions", type_="unique")
