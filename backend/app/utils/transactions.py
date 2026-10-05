"""transaction() context manager: commit on success, rollback on error."""
from contextlib import contextmanager

from app.extensions import db


@contextmanager
def transaction():
    try:
        yield
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
