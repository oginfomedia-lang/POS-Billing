"""products.plu_code: the weighing-scale item code for loose items

Revision ID: c3f7a9d2e5b1
Revises: b8e4c2a6d9f1, e2f3a4b5c6d7 (also merges the two migration heads)
Create Date: 2026-10-13

Loose items whose SKU is a plain number (how scale stickers were matched until now) get that number as
their scale code, so stickers that scan today keep working.
"""
from alembic import op
import sqlalchemy as sa


revision = "c3f7a9d2e5b1"
down_revision = ("b8e4c2a6d9f1", "e2f3a4b5c6d7")
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("plu_code", sa.String(length=6), nullable=True))
    op.create_index(
        "uq_products_plu_code", "products", ["plu_code"],
        unique=True, postgresql_where=sa.text("plu_code IS NOT NULL"),
    )
    # One product per code: if two loose items share a numeric SKU value, only the lowest id gets it.
    op.execute("""
        UPDATE products p SET plu_code = s.code
        FROM (
            SELECT DISTINCT ON (CAST(CAST(sku AS BIGINT) AS TEXT))
                   id, CAST(CAST(sku AS BIGINT) AS TEXT) AS code
            FROM products
            WHERE is_variable_weight AND is_active AND sku ~ '^[0-9]{1,6}$'
            ORDER BY CAST(CAST(sku AS BIGINT) AS TEXT), id
        ) s
        WHERE p.id = s.id
    """)


def downgrade():
    op.drop_index("uq_products_plu_code", table_name="products")
    op.drop_column("products", "plu_code")
