"""Schemas for supplier document uploads."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import DocumentEntityType


class SupplierDocumentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    entity_type: DocumentEntityType
    entity_id: int
    document_label: str | None
    original_filename: str
    file_size: int | None
    mime_type: str | None
    uploaded_by_id: int | None
    created_at: datetime
