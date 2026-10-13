"""merge multiple migration heads

Revision ID: 0681aa0e55cb
Revises: b8e4c2a6d9f1, e2f3a4b5c6d7
Create Date: 2026-10-12 11:36:46.489309

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0681aa0e55cb'
down_revision = ('b8e4c2a6d9f1', 'e2f3a4b5c6d7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
