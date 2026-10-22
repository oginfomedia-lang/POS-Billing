"""users.pin_failures / pin_locked_until: lock a user for a few minutes after too many wrong PINs

Revision ID: d4a8b2e6f3c1
Revises: c7e2a4f8d1b9
Create Date: 2026-10-20

Stops guessing a manager's PIN through the discount / return approval box, and brute-forcing logins.
Existing users start with no failures and no lock.
"""
from alembic import op
import sqlalchemy as sa

from app.utils.migration_guards import add_column_if_missing


revision = "d4a8b2e6f3c1"
down_revision = "c7e2a4f8d1b9"
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_missing("users", sa.Column("pin_failures", sa.Integer(), nullable=False, server_default="0"))
    add_column_if_missing("users", sa.Column("pin_locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("users", "pin_locked_until")
    op.drop_column("users", "pin_failures")
