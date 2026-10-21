"""users.must_change_pin: choose your own PIN on first login

Revision ID: b9d3e7f2a6c4
Revises: a2f5c8e1d4b7
Create Date: 2026-10-21

Anyone still using the installer's default PIN (admin123) has to change it at their next login.
"""
from alembic import op
import sqlalchemy as sa
from werkzeug.security import check_password_hash


revision = "b9d3e7f2a6c4"
down_revision = "a2f5c8e1d4b7"
branch_labels = None
depends_on = None

DEFAULT_PIN = "admin123"


def upgrade():
    op.add_column(
        "users", sa.Column("must_change_pin", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    conn = op.get_bind()
    for uid, pin_hash in conn.execute(sa.text("SELECT id, pin_hash FROM users")).all():
        if check_password_hash(pin_hash, DEFAULT_PIN):
            conn.execute(sa.text("UPDATE users SET must_change_pin = true WHERE id = :id"), {"id": uid})


def downgrade():
    op.drop_column("users", "must_change_pin")
