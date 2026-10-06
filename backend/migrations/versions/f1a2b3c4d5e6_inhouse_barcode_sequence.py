"""inhouse barcode sequence

Revision ID: f1a2b3c4d5e6
Revises: c82f91041d8e
Create Date: 2026-10-06

Numbers for in-house barcodes (290 + 9 digits + check digit). Autogenerate doesn't
detect sequences, so this migration is hand-written.
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "c82f91041d8e"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.schema.CreateSequence(sa.Sequence("inhouse_barcode_seq")))


def downgrade():
    op.execute(sa.schema.DropSequence(sa.Sequence("inhouse_barcode_seq")))
