"""transaction() context manager: commit on success, rollback on error.

Nesting: a transaction() opened inside another one joins it. Only the outermost one commits (or rolls back), so
several service calls can be grouped into one unit of work: all of them are saved, or none is
(e.g. direct_purchase_service: PO + goods receipt + invoice).

Rule for code inside a transaction(): never call db.session.commit() / rollback() yourself; raise an exception
to undo everything.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from app.extensions import db

# How many transaction() blocks are open right now in this request / thread.
_depth: ContextVar[int] = ContextVar("transaction_depth", default=0)


@contextmanager
def transaction():
    depth = _depth.get()
    token = _depth.set(depth + 1)
    try:
        yield
        if depth == 0:
            db.session.commit()  # outermost block: save everything
    except Exception:
        if depth == 0:
            db.session.rollback()  # outermost block: undo everything
        raise  # inner block: let it travel up to the outermost one
    finally:
        _depth.reset(token)
