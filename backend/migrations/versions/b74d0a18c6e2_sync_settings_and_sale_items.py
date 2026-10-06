"""sync settings and sale item schema

Revision ID: b74d0a18c6e2
Revises: e9629c99c2ef
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa


revision = "b74d0a18c6e2"
down_revision = "e9629c99c2ef"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_system_settings_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_system_settings")),
    )
    op.add_column(
        "sale_items",
        sa.Column(
            "discount_amount",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("sale_items", "discount_amount")
    op.drop_table("system_settings")
