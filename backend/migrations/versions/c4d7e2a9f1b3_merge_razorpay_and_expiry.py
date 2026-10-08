"""merge razorpay payments and expiry tracking branches

Both came from different points of the chain (9b1e5c7a2d40 after store_price_override,
a1b2c3d4e5f6 after add_uom_to_products). This only joins them; it changes nothing in the database.

Revision ID: c4d7e2a9f1b3
Revises: 9b1e5c7a2d40, a1b2c3d4e5f6
Create Date: 2026-10-08
"""

revision = "c4d7e2a9f1b3"
down_revision = ("9b1e5c7a2d40", "a1b2c3d4e5f6")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
