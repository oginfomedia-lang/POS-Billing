"""Reading supplier bills: supplier_item_aliases (bill text → product) and supplier_bill_templates (column layout)

Revision ID: d6b3f8a1c5e2
Revises: c4e8a2f6b9d1
Create Date: 2026-11-18
"""
from alembic import op
import sqlalchemy as sa


revision = "d6b3f8a1c5e2"
down_revision = "c4e8a2f6b9d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_item_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description_key", sa.String(400), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("supplier_id", "description_key", name="uq_supplier_item_aliases_supplier_key"),
    )
    op.create_index("ix_supplier_item_aliases_supplier_id", "supplier_item_aliases", ["supplier_id"])
    op.create_index("ix_supplier_item_aliases_product_id", "supplier_item_aliases", ["product_id"])

    op.create_table(
        "supplier_bill_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("supplier_id", name="uq_supplier_bill_templates_supplier"),
    )


def downgrade():
    op.drop_table("supplier_bill_templates")
    op.drop_index("ix_supplier_item_aliases_product_id", table_name="supplier_item_aliases")
    op.drop_index("ix_supplier_item_aliases_supplier_id", table_name="supplier_item_aliases")
    op.drop_table("supplier_item_aliases")