"""create discounts table

Revision ID: d3a1c9f42b7e
Revises: b74d0a18c6e2
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d3a1c9f42b7e"
down_revision = "b74d0a18c6e2"
branch_labels = None
depends_on = None


def upgrade():
    discount_type = postgresql.ENUM(
        "PERCENTAGE", "FIXED", name="discount_type", create_type=False
    )
    discount_scope = postgresql.ENUM(
        "BILL", "PRODUCT", "CATEGORY", name="discount_scope", create_type=False
    )
    discount_type.create(op.get_bind(), checkfirst=True)
    discount_scope.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "discounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("discount_type", discount_type, nullable=False),
        sa.Column("value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("scope", discount_scope, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("store_id", sa.Integer(), nullable=True),
        sa.Column("min_bill_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("value > 0", name=op.f("ck_discounts_value_positive")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_discounts_category_id_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_discounts_product_id_products"),
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            name=op.f("fk_discounts_store_id_stores"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discounts")),
    )


def downgrade():
    op.drop_table("discounts")
    sa.Enum(name="discount_scope").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="discount_type").drop(op.get_bind(), checkfirst=True)
