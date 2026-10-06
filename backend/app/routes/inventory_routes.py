"""Stock-in, adjustment, damage, ledger and low-stock endpoints."""
from flask import Blueprint, jsonify, request

from app.errors.exceptions import ValidationError
from app.schemas.inventory_schemas import AdjustStockRequest, InventoryTxnOut, StockInRequest, ThresholdRequest
from app.services import auth_service, inventory_service
from app.utils.permissions import require_permission

inventory_bp = Blueprint("inventory", __name__)


def _store_id_arg() -> int:
    store_id = request.args.get("store_id", type=int)
    if store_id is None:
        raise ValidationError("store_id query parameter is required.")
    return store_id


@inventory_bp.get("/inventory")
@require_permission("inventory.read")
def stock_levels():
    levels = inventory_service.stock_levels(_store_id_arg())
    return jsonify([lv.model_dump(mode="json") for lv in levels]), 200


@inventory_bp.post("/inventory/stock-in")
@require_permission("inventory.manage")
def stock_in():
    data = StockInRequest.model_validate(request.get_json(force=True))
    row = inventory_service.stock_in(data, auth_service.current_user())
    return jsonify({"product_id": row.product_id, "qty_on_hand": str(row.qty_on_hand)}), 200


@inventory_bp.post("/inventory/adjust")
@require_permission("inventory.manage")
def adjust():
    data = AdjustStockRequest.model_validate(request.get_json(force=True))
    row = inventory_service.adjust(data, auth_service.current_user())
    return jsonify({"product_id": row.product_id, "qty_on_hand": str(row.qty_on_hand)}), 200


@inventory_bp.post("/inventory/threshold")
@require_permission("inventory.manage")
def set_threshold():
    data = ThresholdRequest.model_validate(request.get_json(force=True))
    row = inventory_service.set_threshold(data, auth_service.current_user())
    threshold = None if row.low_stock_threshold is None else str(row.low_stock_threshold)
    return jsonify({"product_id": row.product_id, "low_stock_threshold": threshold}), 200


@inventory_bp.get("/inventory/ledger")
@require_permission("inventory.read")
def ledger():
    product_id = request.args.get("product_id", type=int)
    txns = inventory_service.ledger(_store_id_arg(), product_id)
    return jsonify([InventoryTxnOut.model_validate(t).model_dump(mode="json") for t in txns]), 200
