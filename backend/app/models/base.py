"""Common model mixins (id, created_at, updated_at)."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declared_attr


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    @declared_attr
    def created_at(cls):  # noqa: N805
        return Column(DateTime(timezone=True), default=_now, nullable=False)

    @declared_attr
    def updated_at(cls):  # noqa: N805
        return Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
