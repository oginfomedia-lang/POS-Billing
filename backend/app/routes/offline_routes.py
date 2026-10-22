"""Offline billing: catalogue download for counters, and upload of bills made while the server was unreachable."""
from flask import Blueprint, jsonify, request

from app.errors.exceptions import ValidationError
from app.schemas.offline_schemas import OfflineSaleIn
from app.schemas.sale_schemas import SaleOut
from app.services import auth_service, offline_service
from app.utils.permissions import require_permission
from app.utils.store_scope import require_store_access

offline_bp = Blueprint("offline", __name__)


@offline_bp.get("/pos/offline-catalog")
@require_permission("sales.create")
def offline_catalog():
    """?store_id=: products, this store's prices, offers and receipt details, for billing without the server."""
    store_id = request.args.get("store_id", type=int)
    if store_id is None:
        raise ValidationError("store_id query parameter is required.")
    require_store_access(auth_service.current_user(), store_id)
    return jsonify(offline_service.catalog(store_id).model_dump(mode="json")), 200


@offline_bp.post("/sales/offline")
@require_permission("sales.create")
def upload_offline_sale():
    data = OfflineSaleIn.model_validate(request.get_json(force=True))
    sale, created = offline_service.record_sale(data, auth_service.current_user())
    return jsonify(SaleOut.model_validate(sale).model_dump(mode="json")), 201 if created else 200
