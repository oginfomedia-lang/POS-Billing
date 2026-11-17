"""purchase orders: record how the PO reached the supplier (email / WhatsApp / phone / in person)

Revision ID: a3d8f1c6e2b9
Revises: e5a1c7d3f9b2
Create Date: 2026-11-02

sent_* = the first confirmed send (by email, or marked by staff). email_* = the latest automatic email attempt.
"""
from alembic import op
import sqlalchemy as sa


revision = "a3d8f1c6e2b9"
down_revision = "e5a1c7d3f9b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("purchase_orders", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("purchase_orders", sa.Column("sent_via", sa.String(20), nullable=True))
    op.add_column("purchase_orders", sa.Column("sent_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_purchase_orders_sent_by_id_users", "purchase_orders", "users", ["sent_by_id"], ["id"]
    )
    op.add_column("purchase_orders", sa.Column("email_status", sa.String(20), nullable=True))
    op.add_column("purchase_orders", sa.Column("email_to", sa.String(200), nullable=True))
    op.add_column("purchase_orders", sa.Column("email_error", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("purchase_orders", "email_error")
    op.drop_column("purchase_orders", "email_to")
    op.drop_column("purchase_orders", "email_status")
    op.drop_constraint("fk_purchase_orders_sent_by_id_users", "purchase_orders", type_="foreignkey")
    op.drop_column("purchase_orders", "sent_by_id")
    op.drop_column("purchase_orders", "sent_via")
    op.drop_column("purchase_orders", "sent_at")
