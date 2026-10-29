"""product_sku_seq: the number in automatic SKUs (KIR-SAK-0001)

Existing products keep their SKUs: nothing is renamed. products.sku is already NOT NULL and UNIQUE
(uq_products_sku); this checks that before relying on it, and stops with the offending SKUs if a database
somehow has blank or duplicate ones, so they can be fixed by hand first.

Revision ID: e5a1c7d3f9b2
Revises: d2b7f5a9c1e8
Create Date: 2026-10-23
"""
from alembic import op
import sqlalchemy as sa

from app.utils.migration_guards import has_constraint


revision = "e5a1c7d3f9b2"
down_revision = "d2b7f5a9c1e8"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    blank = conn.execute(sa.text("SELECT id FROM products WHERE sku IS NULL OR btrim(sku) = '' LIMIT 20")).scalars().all()
    dupes = conn.execute(sa.text(
        "SELECT sku FROM products GROUP BY sku HAVING count(*) > 1 LIMIT 20")).scalars().all()
    if blank or dupes:
        raise RuntimeError(
            f"Products need a unique SKU before upgrading. Blank SKU (product ids): {blank}. Duplicates: {dupes}."
        )
    if not has_constraint("products", "uq_products_sku"):
        op.create_unique_constraint("uq_products_sku", "products", ["sku"])
    op.execute("CREATE SEQUENCE IF NOT EXISTS product_sku_seq")


def downgrade():
    op.execute("DROP SEQUENCE IF EXISTS product_sku_seq")
