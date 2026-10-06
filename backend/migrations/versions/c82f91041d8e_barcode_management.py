"""barcode management schema updates

Revision ID: c82f91041d8e
Revises: d3a1c9f42b7e
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "c82f91041d8e"
down_revision = "d3a1c9f42b7e"
branch_labels = None
depends_on = None


def upgrade():
    # Create Enum type for Postgres
    barcode_type_enum = sa.Enum("MANUFACTURER", "IN_HOUSE", "PRICE_EMBEDDED", name="barcodetype")
    barcode_type_enum.create(op.get_bind(), checkfirst=True)

    # 1. Add is_variable_weight to products
    op.add_column(
        "products",
        sa.Column("is_variable_weight", sa.Boolean(), server_default="false", nullable=False),
    )

    # 2. Add sku to products
    op.add_column(
        "products",
        sa.Column("sku", sa.String(length=50), nullable=True),
    )

    # Populate default SKU for existing rows
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE products SET sku = 'SKU-' || id WHERE sku IS NULL"))

    # Alter sku to nullable=False and unique
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.alter_column("sku", nullable=False)
        batch_op.create_unique_constraint(batch_op.f("uq_products_sku"), ["sku"])

    # 3. Add barcode_type and created_at to product_barcodes
    with op.batch_alter_table("product_barcodes", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("barcode_type", barcode_type_enum, server_default="MANUFACTURER", nullable=False)
        )
        batch_op.add_column(
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False)
        )

    # 4. Alter sale_items.qty to Numeric(12, 3) to support decimal quantities (e.g. 1.500 kg)
    with op.batch_alter_table("sale_items", schema=None) as batch_op:
        batch_op.alter_column(
            "qty",
            type_=sa.Numeric(precision=12, scale=3),
            existing_type=sa.Integer(),
            nullable=False,
        )


def downgrade():
    with op.batch_alter_table("sale_items", schema=None) as batch_op:
        batch_op.alter_column(
            "qty",
            type_=sa.Integer(),
            existing_type=sa.Numeric(precision=12, scale=3),
            nullable=False,
        )

    with op.batch_alter_table("product_barcodes", schema=None) as batch_op:
        batch_op.drop_column("created_at")
        batch_op.drop_column("barcode_type")

    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_products_sku"), type_="unique")
        batch_op.drop_column("sku")
        batch_op.drop_column("is_variable_weight")

    sa.Enum(name="barcodetype").drop(op.get_bind(), checkfirst=True)
