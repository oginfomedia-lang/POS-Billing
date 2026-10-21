"""users.session_version: a PIN reset (or new role / store, or deactivation) ends that user's open sessions

Revision ID: c7e2a4f8d1b9
Revises: b3d6f9a2c8e1
Create Date: 2026-10-20

Every user starts at 0, the value tokens issued before this change are read as, so nobody is logged out
by the upgrade itself.
"""
from alembic import op
import sqlalchemy as sa

from app.utils.migration_guards import add_column_if_missing


revision = "c7e2a4f8d1b9"
down_revision = "b3d6f9a2c8e1"
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_missing("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("users", "session_version")
