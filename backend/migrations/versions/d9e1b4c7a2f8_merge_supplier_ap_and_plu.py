"""merge the supplier AP / cloud backup head with the loose-item (plu_code) head

Revision ID: d9e1b4c7a2f8
Revises: b1c2d3e4f5a6, c3f7a9d2e5b1
Create Date: 2026-10-13

Two branches were merged into main the same day, each ending in its own migration; without this,
`flask db upgrade` stops with "Multiple head revisions are present".
"""

revision = "d9e1b4c7a2f8"
down_revision = ("b1c2d3e4f5a6", "c3f7a9d2e5b1")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
