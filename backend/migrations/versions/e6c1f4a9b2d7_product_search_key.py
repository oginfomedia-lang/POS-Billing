"""products.search_key: sound-alike name, so English letters find Marathi names ("madhur" -> "मधुर साखर")

Revision ID: e6c1f4a9b2d7
Revises: d4a8b2e6f3c1
Create Date: 2026-10-20

Fills the key for every existing product. New and edited products get it automatically (app/models/product.py).
"""
from alembic import op
import sqlalchemy as sa

from app.utils.search_key import search_key


revision = "e6c1f4a9b2d7"
down_revision = "d4a8b2e6f3c1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("search_key", sa.String(length=400), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM products")).all()
    for pid, name in rows:
        conn.execute(sa.text("UPDATE products SET search_key = :k WHERE id = :id"), {"k": search_key(name), "id": pid})


def downgrade():
    op.drop_column("products", "search_key")
