"""sales.offline_id: bills made on a counter while the server was unreachable

Revision ID: d2b7f5a9c1e8
Revises: c4e8a1f6b3d9
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa


revision = "d2b7f5a9c1e8"
down_revision = "c4e8a1f6b3d9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sales", sa.Column("offline_id", sa.String(length=36), nullable=True))
    op.create_unique_constraint("sales_offline_id_key", "sales", ["offline_id"])


def downgrade():
    op.drop_constraint("sales_offline_id_key", "sales", type_="unique")
    op.drop_column("sales", "offline_id")
