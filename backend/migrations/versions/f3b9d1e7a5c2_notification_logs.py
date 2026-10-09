"""notification_logs for the nightly WhatsApp collection summary

Revision ID: f3b9d1e7a5c2
Revises: e7f9a1c3b5d2
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa


revision = "f3b9d1e7a5c2"
down_revision = "e7f9a1c3b5d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("recipient", sa.String(length=15), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SENT", "FAILED", name="notification_status"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=100), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "report_date", "store_id", "recipient", name="uq_notification_once"),
    )


def downgrade():
    op.drop_table("notification_logs")
    sa.Enum(name="notification_status").drop(op.get_bind(), checkfirst=True)
