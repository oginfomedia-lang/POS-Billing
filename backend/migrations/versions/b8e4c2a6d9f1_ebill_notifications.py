"""notification_logs.sale_id for the WhatsApp e-bill

Revision ID: b8e4c2a6d9f1
Revises: a9c4e2f7b1d3, f3b9d1e7a5c2 (also merges the two migration heads)
Create Date: 2026-10-10

uq_notification_once becomes a partial unique index (daily report rows only), so one customer can get an
e-bill for every bill they make on the same day; uq_notification_ebill stops the same bill going twice.
"""
from alembic import op
import sqlalchemy as sa


revision = "b8e4c2a6d9f1"
down_revision = ("a9c4e2f7b1d3", "f3b9d1e7a5c2")
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notification_logs", sa.Column("sale_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_notification_logs_sale_id", "notification_logs", "sales", ["sale_id"], ["id"])
    op.create_index("ix_notification_logs_sale_id", "notification_logs", ["sale_id"])
    op.drop_constraint("uq_notification_once", "notification_logs", type_="unique")
    op.create_index(
        "uq_notification_once", "notification_logs", ["kind", "report_date", "store_id", "recipient"],
        unique=True, postgresql_where=sa.text("sale_id IS NULL"),
    )
    op.create_index(
        "uq_notification_ebill", "notification_logs", ["sale_id", "recipient"],
        unique=True, postgresql_where=sa.text("sale_id IS NOT NULL"),
    )


def downgrade():
    op.execute("DELETE FROM notification_logs WHERE sale_id IS NOT NULL")
    op.drop_index("uq_notification_ebill", table_name="notification_logs")
    op.drop_index("uq_notification_once", table_name="notification_logs")
    op.create_unique_constraint(
        "uq_notification_once", "notification_logs", ["kind", "report_date", "store_id", "recipient"]
    )
    op.drop_index("ix_notification_logs_sale_id", table_name="notification_logs")
    op.drop_constraint("fk_notification_logs_sale_id", "notification_logs", type_="foreignkey")
    op.drop_column("notification_logs", "sale_id")
