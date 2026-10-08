"""Pagination and common response schemas."""
from __future__ import annotations

import math
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationQuery(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(25, ge=1, le=100)
    # ?status=active / ?status=inactive lists only those; omitted lists everything.
    status: Literal["active", "inactive"] | None = None

    @property
    def is_active(self) -> bool | None:
        return None if self.status is None else self.status == "active"


class PagedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int

    @classmethod
    def build(
        cls,
        items: list,
        total: int,
        page: int,
        per_page: int,
    ) -> "PagedResponse":
        pages = math.ceil(total / per_page) if per_page else 0
        return cls(items=items, total=total, page=page, per_page=per_page, pages=pages)
