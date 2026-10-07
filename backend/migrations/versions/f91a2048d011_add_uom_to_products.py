"""add uom to products

Revision ID: f91a2048d011
Revises: c82f91041d8e
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "f91a2048d011"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    # Create Enum type for Postgres
    uom_enum = sa.Enum("pcs", "kg", "g", "ltr", "ml", "pack", name="uomtype")
    uom_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "products",
        sa.Column("uom", uom_enum, server_default="pcs", nullable=False),
    )


def downgrade():
    op.drop_column("products", "uom")
    sa.Enum(name="uomtype").drop(op.get_bind(), checkfirst=True)
