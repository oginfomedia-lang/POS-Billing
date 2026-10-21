"""One barcode per product: unique product_barcodes.product_id

Revision ID: a2f5c8e1d4b7
Revises: e6c1f4a9b2d7
Create Date: 2026-10-21

A product that has several barcodes keeps one: its primary barcode, else the oldest. The others are deleted
and written to the audit log, so they can be found again.
"""
import json

from alembic import op
import sqlalchemy as sa


revision = "a2f5c8e1d4b7"
down_revision = "e6c1f4a9b2d7"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    extra = conn.execute(sa.text(
        """
        SELECT id, product_id, barcode FROM (
            SELECT id, product_id, barcode,
                   ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY is_primary DESC, created_at, id) AS n
            FROM product_barcodes
        ) ranked
        WHERE n > 1
        """
    )).all()
    for bid, pid, code in extra:
        conn.execute(
            sa.text(
                "INSERT INTO audit_logs (username, action, entity_type, entity_id, old_values, created_at) "
                "VALUES ('system', 'product.barcode_removed', 'product', :pid, CAST(:old AS JSONB), now())"
            ),
            {"pid": str(pid), "old": json.dumps({"barcode": code, "reason": "one barcode per product"})},
        )
        conn.execute(sa.text("DELETE FROM product_barcodes WHERE id = :id"), {"id": bid})
    conn.execute(sa.text("UPDATE product_barcodes SET is_primary = true WHERE NOT is_primary"))
    op.create_unique_constraint("uq_product_barcodes_product_id", "product_barcodes", ["product_id"])


def downgrade():
    op.drop_constraint("uq_product_barcodes_product_id", "product_barcodes", type_="unique")
