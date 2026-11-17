"""selling-price review: a target profit % per category, and the cost a product's price was last reviewed at

Revision ID: f2d5c8e1a7b4
Revises: e1c4b7a9d2f3
Create Date: 2026-11-16

categories.target_margin_percent: profit wanted on cost (12 = sell at cost × 1.12 before GST). NULL = the parent
category's, else the default in Settings.
products.price_reviewed_cost: the cost price when someone last applied or kept this product's selling price. The
product is not asked about again until its cost changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "f2d5c8e1a7b4"
down_revision = "e1c4b7a9d2f3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("categories", sa.Column("target_margin_percent", sa.Numeric(6, 2), nullable=True))
    op.create_check_constraint(
        "ck_categories_target_margin_range", "categories",
        "target_margin_percent IS NULL OR (target_margin_percent >= 0 AND target_margin_percent <= 1000)",
    )
    op.add_column("products", sa.Column("price_reviewed_cost", sa.Numeric(12, 4), nullable=True))


def downgrade():
    op.drop_column("products", "price_reviewed_cost")
    op.drop_constraint("ck_categories_target_margin_range", "categories", type_="check")
    op.drop_column("categories", "target_margin_percent")
