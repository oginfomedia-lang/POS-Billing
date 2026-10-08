"""merge migration heads

Revision ID: 0f5ec6faaded
Revises: a1b2c3d4e5f6, b5d2e8f1a3c7
Create Date: 2026-10-08 12:28:36.494863

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0f5ec6faaded'
down_revision = ('a1b2c3d4e5f6', 'b5d2e8f1a3c7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
