"""supplier invoices: received value, payable amount, difference reason; one invoice per GRN

Revision ID: e5a8c1f3b7d2
Revises: d9e1b4c7a2f8
Create Date: 2026-10-13

Payments are made against the supplier's invoice and never exceed the value of the goods received.
Existing invoices (e.g. the automatic "INV-<PO>" ones from the old PO quick payment) keep their total as
the payable amount.
"""
from alembic import op
import sqlalchemy as sa


revision = "e5a8c1f3b7d2"
down_revision = "d9e1b4c7a2f8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("supplier_invoices", sa.Column("received_value", sa.Numeric(12, 2), nullable=True))
    op.add_column("supplier_invoices", sa.Column("payable_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("supplier_invoices", sa.Column("difference_reason", sa.Text(), nullable=True))
    op.execute("UPDATE supplier_invoices SET payable_amount = grand_total")
    op.alter_column("supplier_invoices", "payable_amount", nullable=False, server_default="0")

    dup = op.get_bind().execute(sa.text(
        "SELECT goods_receipt_id FROM supplier_invoice_grns GROUP BY goods_receipt_id HAVING COUNT(*) > 1 LIMIT 5"
    )).scalars().all()
    if dup:
        raise RuntimeError(
            f"GRNs {dup} are linked to more than one supplier invoice. Unlink the extra invoices first."
        )
    op.create_unique_constraint(
        "uq_supplier_invoice_grns_goods_receipt", "supplier_invoice_grns", ["goods_receipt_id"]
    )


def downgrade():
    op.drop_constraint("uq_supplier_invoice_grns_goods_receipt", "supplier_invoice_grns", type_="unique")
    op.drop_column("supplier_invoices", "difference_reason")
    op.drop_column("supplier_invoices", "payable_amount")
    op.drop_column("supplier_invoices", "received_value")
