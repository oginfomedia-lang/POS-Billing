"""counters: code and name unique per store (every branch can have its own C01 / "Counter 1")

Revision ID: b3d6f9a2c8e1
Revises: a7c3e9f1b2d4
Create Date: 2026-10-20

Before: a counter code was unique across all stores, and names could repeat inside a store.
After:  (store_id, code) is unique, and (store_id, lower(label)) is unique.

Existing data: codes were globally unique, so no code clashes are possible. Two counters of the same store
with the same name (any letter case) are kept; every one after the first gets its code added to its name,
e.g. "Counter 1" -> "Counter 1 (C02)". Nothing is deleted. Bills keep their bill numbers.
"""
from alembic import op
import sqlalchemy as sa

from app.utils.migration_guards import has_constraint, has_index


revision = "b3d6f9a2c8e1"
down_revision = "a7c3e9f1b2d4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE counters AS c
        SET label = left(c.label, 100 - length(c.code) - 3) || ' (' || c.code || ')'
        FROM (
            SELECT id, row_number() OVER (PARTITION BY store_id, lower(label) ORDER BY id) AS n
            FROM counters
        ) AS d
        WHERE c.id = d.id AND d.n > 1
        """
    )
    # Each step is skipped when it's already done (a shop installed from a build made while this was being written).
    if has_constraint("counters", "uq_counters_code"):
        op.drop_constraint("uq_counters_code", "counters", type_="unique")
    if not has_constraint("counters", "uq_counters_store_id_code"):
        op.create_unique_constraint("uq_counters_store_id_code", "counters", ["store_id", "code"])
    if not has_index("counters", "uq_counters_store_id_label"):
        op.create_index("uq_counters_store_id_label", "counters", ["store_id", sa.text("lower(label)")], unique=True)


def downgrade():
    clash = op.get_bind().execute(
        sa.text("SELECT code FROM counters GROUP BY code HAVING count(*) > 1 LIMIT 5")
    ).scalars().all()
    if clash:
        raise RuntimeError(
            "Can't go back to one counter code for all stores: these codes are used in more than one store: "
            + ", ".join(clash) + ". Rename them first."
        )
    op.drop_index("uq_counters_store_id_label", table_name="counters")
    op.drop_constraint("uq_counters_store_id_code", "counters", type_="unique")
    op.create_unique_constraint("uq_counters_code", "counters", ["code"])
