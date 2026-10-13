"""Secure document upload/download/list routes for supplier documents."""
from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.errors.exceptions import BadRequestError
from app.extensions import db
from app.models.enums import DocumentEntityType
from app.models.user import User
from app.services import upload_service
from app.utils.permissions import require_permission

upload_bp = Blueprint("uploads", __name__)


def _current_user() -> User | None:
    try:
        verify_jwt_in_request()
        return db.session.get(User, int(get_jwt_identity()))
    except Exception:
        return None


@upload_bp.post("/documents/upload")
@require_permission("documents.upload")
def upload_document():
    """Upload a supplier-related document (multipart/form-data)."""
    file = request.files.get("file")
    if not file:
        raise BadRequestError("No file provided in request.")
    entity_type_raw = request.form.get("entity_type", "")
    entity_id_raw = request.form.get("entity_id", "")
    if not entity_type_raw or not entity_id_raw:
        raise BadRequestError("entity_type and entity_id are required form fields.")
    try:
        entity_type = DocumentEntityType(entity_type_raw)
    except ValueError:
        raise BadRequestError(f"Invalid entity_type '{entity_type_raw}'.")
    try:
        entity_id = int(entity_id_raw)
    except ValueError:
        raise BadRequestError("entity_id must be an integer.")
    document_label = request.form.get("document_label")
    doc = upload_service.save_document(file, entity_type, entity_id, document_label, _current_user())
    return jsonify(doc.model_dump(mode="json")), 201


@upload_bp.get("/documents")
@require_permission("documents.upload")
def list_documents():
    entity_type_raw = request.args.get("entity_type", "")
    entity_id = request.args.get("entity_id", type=int)
    if not entity_type_raw or not entity_id:
        raise BadRequestError("entity_type and entity_id query params are required.")
    try:
        entity_type = DocumentEntityType(entity_type_raw)
    except ValueError:
        raise BadRequestError(f"Invalid entity_type '{entity_type_raw}'.")
    docs = upload_service.list_documents(entity_type, entity_id)
    return jsonify([d.model_dump(mode="json") for d in docs]), 200


@upload_bp.get("/documents/<int:doc_id>/download")
@require_permission("documents.upload")
def download_document(doc_id: int):
    path, original_filename, mime_type = upload_service.get_document_path(doc_id)
    return send_file(
        path,
        mimetype=mime_type,
        as_attachment=True,
        download_name=original_filename,
    )


@upload_bp.delete("/documents/<int:doc_id>")
@require_permission("documents.delete")
def delete_document(doc_id: int):
    upload_service.delete_document(doc_id, _current_user())
    return jsonify({"message": "Deleted."}), 200
