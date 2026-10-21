"""Checks for migrations (imported as app.utils.migration_guards) that may meet a database where their change is already there.

A shop installed from a build made while a feature was still being written can have a column, table or
constraint that a later migration adds "for the first time" (e.g. products.search_key). These helpers let such
migrations skip what already exists instead of failing the whole upgrade.
"""
import sqlalchemy as sa
from alembic import op


def _insp():
    return sa.inspect(op.get_bind())


def has_table(table: str) -> bool:
    return _insp().has_table(table)


def has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _insp().get_columns(table))


def has_constraint(table: str, name: str) -> bool:
    """A unique constraint (or unique index) with this name on the table."""
    insp = _insp()
    names = {c["name"] for c in insp.get_unique_constraints(table)} | {i["name"] for i in insp.get_indexes(table)}
    return name in names


def has_index(table: str, name: str) -> bool:
    return any(i["name"] == name for i in _insp().get_indexes(table))


def add_column_if_missing(table: str, column: sa.Column) -> None:
    if not has_column(table, column.name):
        op.add_column(table, column)
