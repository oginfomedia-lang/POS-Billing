"""Secure file upload and retrieval for supplier documents."""
from __future__ import annotations

import mimetypes
import os
import re
import uuid
from pathlib import Path

from flask import current_app
from werkzeug.datastructures import FileStorage

from app.errors.exceptions import BadRequestError, NotFoundError
from app.extensions import db
from app.models.enums import DocumentEntityType
from app.models.supplier_document import SupplierDocument
from app.models.user import User
from app.schemas.supplier_document_schemas import SupplierDocumentOut
from app.services import audit_service
from app.utils.transactions import transaction

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/tiff",
}

_UNSAFE_CHARS = re.compile(r'[^\w.\-]')


def _upload_dir() -> Path:
    configured = current_app.config.get("UPLOAD_DIR")
    if configured:
        d = Path(configured)
    else:
        d = Path.home() / "pos_uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_filename(name: str) -> str:
    name = Path(name).name
    name = _UNSAFE_CHARS.sub("_", name)
    return name[:200] if name else "file"


def save_document(
    file: FileStorage,
    entity_type: DocumentEntityType,
    entity_id: int,
    document_label: str | None,
    actor: User | None,
) -> SupplierDocumentOut:
    if not file or not file.filename:
        raise BadRequestError("No file provided.")

    mime = file.mimetype or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    if mime not in ALLOWED_MIME_TYPES:
        raise BadRequestError(
            f"File type '{mime}' is not allowed. Permitted: PDF, JPEG, PNG, GIF, WebP, TIFF."
        )

    max_bytes: int = current_app.config.get("UPLOAD_MAX_BYTES", 20 * 1024 * 1024)
    content = file.read()
    if len(content) > max_bytes:
        raise BadRequestError(
            f"File size {len(content):,} bytes exceeds maximum {max_bytes:,} bytes."
        )
    file.seek(0)

    ext = Path(file.filename).suffix.lower() or mimetypes.guess_extension(mime) or ""
    stored = f"{uuid.uuid4().hex}{ext}"
    dest = _upload_dir() / stored
    dest.write_bytes(content)

    with transaction():
        doc = SupplierDocument(
            entity_type=entity_type,
            entity_id=entity_id,
            document_label=document_label,
            original_filename=_safe_filename(file.filename),
            stored_filename=stored,
            file_size=len(content),
            mime_type=mime,
            uploaded_by_id=actor.id if actor else None,
        )
        db.session.add(doc)
        db.session.flush()
        audit_service.log(
            actor, "document.upload", "supplier_document", doc.id,
            new_values={"entity_type": entity_type.value, "entity_id": entity_id, "filename": doc.original_filename},
        )
    return SupplierDocumentOut.model_validate(doc)


def list_documents(entity_type: DocumentEntityType, entity_id: int) -> list[SupplierDocumentOut]:
    from sqlalchemy import select
    rows = db.session.scalars(
        select(SupplierDocument)
        .where(SupplierDocument.entity_type == entity_type)
        .where(SupplierDocument.entity_id == entity_id)
        .order_by(SupplierDocument.id)
    ).all()
    return [SupplierDocumentOut.model_validate(r) for r in rows]


def get_document_path(doc_id: int) -> tuple[Path, str, str]:
    """Returns (absolute_path, original_filename, mime_type)."""
    doc = db.session.get(SupplierDocument, doc_id)
    if not doc:
        raise NotFoundError(f"Document #{doc_id} not found.")
    path = _upload_dir() / doc.stored_filename
    if not path.exists():
        raise NotFoundError("Document file not found on disk.")
    return path, doc.original_filename, doc.mime_type or "application/octet-stream"


def delete_document(doc_id: int, actor: User | None) -> None:
    doc = db.session.get(SupplierDocument, doc_id)
    if not doc:
        raise NotFoundError(f"Document #{doc_id} not found.")
    path = _upload_dir() / doc.stored_filename
    with transaction():
        audit_service.log(actor, "document.delete", "supplier_document", doc.id, None, None)
        db.session.delete(doc)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
