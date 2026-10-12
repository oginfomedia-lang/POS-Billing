"""merge final heads

Revision ID: 666ad48a3470
Revises: 17b2cccb514b, e7f9a1c3b5d2
Create Date: 2026-10-09 11:09:14.650350

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '666ad48a3470'
down_revision = ('17b2cccb514b', 'e7f9a1c3b5d2')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
