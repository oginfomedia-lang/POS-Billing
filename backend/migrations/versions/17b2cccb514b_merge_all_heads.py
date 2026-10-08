"""merge all heads

Revision ID: 17b2cccb514b
Revises: 0f5ec6faaded, 9b1e5c7a2d40
Create Date: 2026-10-08 14:26:07.905454

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '17b2cccb514b'
down_revision = ('0f5ec6faaded', '9b1e5c7a2d40')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
