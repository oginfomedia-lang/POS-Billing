"""Stock-in, adjustment, damage, ledger and low-stock endpoints."""
from flask import Blueprint, jsonify, request

from app.errors.exceptions import ValidationError
from app.schemas.inventory_schemas import (
    AdjustStockRequest,
    BatchReturnRequest,
    BatchWriteOffRequest,
    InventoryTxnOut,
    ShelfMinRequest,
    StockInRequest,
    StorePriceRequest,
    ThresholdRequest,
    TransferRequest,
)
from app.services import auth_service, godown_service, inventory_service, supplier_return_service
from app.utils.permissions import require_permission
from app.utils.store_scope import is_head_office, require_store_access

inventory_bp = Blueprint("inventory", __name__)


def _store_id_arg() -> int:
    """The ?store_id= being read; the user must be allowed to see that store."""
    store_id = request.args.get("store_id", type=int)
    if store_id is None:
        raise ValidationError("store_id query parameter is required.")
    require_store_access(auth_service.current_user(), store_id)
    return store_id


@inventory_bp.get("/inventory")
@require_permission("inventory.read")
def stock_levels():
    levels = inventory_service.stock_levels(_store_id_arg(), request.args.get("q", "").strip() or None)
    return jsonify([lv.model_dump(mode="json") for lv in levels]), 200


@inventory_bp.post("/inventory/stock-in")
@require_permission("inventory.manage")
def stock_in():
    data = StockInRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    require_store_access(actor, data.store_id)
    row = inventory_service.stock_in(data, actor)
    return jsonify({"product_id": row.product_id, "qty_on_hand": str(row.qty_on_hand)}), 200


@inventory_bp.post("/inventory/adjust")
@require_permission("inventory.manage")
def adjust():
    data = AdjustStockRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    require_store_access(actor, data.store_id)
    row = inventory_service.adjust(data, actor)
    return jsonify({"product_id": row.product_id, "qty_on_hand": str(row.qty_on_hand)}), 200


@inventory_bp.post("/inventory/threshold")
@require_permission("inventory.manage")
def set_threshold():
    data = ThresholdRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    require_store_access(actor, data.store_id)
    row = inventory_service.set_threshold(data, actor)
    threshold = None if row.low_stock_threshold is None else str(row.low_stock_threshold)
    return jsonify({"product_id": row.product_id, "low_stock_threshold": threshold}), 200


@inventory_bp.post("/inventory/price")
@require_permission("inventory.manage")
def set_store_price():
    """This store's own selling price for a product; {"price": null} goes back to the head-office price."""
    data = StorePriceRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    require_store_access(actor, data.store_id)
    row = inventory_service.set_store_price(data, actor)
    return jsonify({"product_id": row.product_id, "price": None if row.price is None else str(row.price)}), 200


@inventory_bp.get("/inventory/expiring")
@require_permission("inventory.read")
def expiring():
    """Batches expiring within ?days= (default 30) or already expired."""
    days = request.args.get("days", 30, type=int)
    results = inventory_service.expiring_soon(_store_id_arg(), days)
    return jsonify([r.model_dump(mode="json") for r in results]), 200


@inventory_bp.get("/inventory/batches")
@require_permission("inventory.read")
def batches():
    """?store_id=&product_id=: the product's batches with stock, in the order sales take them (FEFO)."""
    product_id = request.args.get("product_id", type=int)
    if product_id is None:
        raise ValidationError("product_id query parameter is required.")
    results = inventory_service.list_batches(_store_id_arg(), product_id)
    return jsonify([r.model_dump(mode="json") for r in results]), 200


@inventory_bp.post("/inventory/batches/<int:batch_id>/write-off")
@require_permission("inventory.manage")
def write_off_batch(batch_id: int):
    data = BatchWriteOffRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    allowed = None if is_head_office(actor) else {actor.store_id}
    batch = inventory_service.write_off_batch(batch_id, data, actor, allowed)
    return jsonify({"batch_id": batch.id, "qty_remaining": str(batch.qty_remaining)}), 200


@inventory_bp.post("/inventory/batches/<int:batch_id>/return-to-supplier")
@require_permission("inventory.manage")
def return_batch_to_supplier(batch_id: int):
    """Goods of a GRN batch go back to its supplier: out of stock, and a debit note for their value."""
    data = BatchReturnRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    allowed = None if is_head_office(actor) else {actor.store_id}
    ret = supplier_return_service.return_batch(batch_id, data, actor, allowed)
    return jsonify(supplier_return_service.enrich(ret).model_dump(mode="json")), 201


@inventory_bp.post("/inventory/transfer")
@require_permission("inventory.manage")
def transfer():
    """Move goods godown → shop shelf (or back): {"store_id", "product_id", "qty", "direction"}."""
    data = TransferRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    require_store_access(actor, data.store_id)
    row = godown_service.transfer(data, actor)
    return jsonify({
        "product_id": row.product_id,
        "shop_qty": str(godown_service.shop_qty(row)),
        "godown_qty": str(row.godown_qty),
    }), 200


@inventory_bp.post("/inventory/shelf-min")
@require_permission("inventory.manage")
def set_shelf_min():
    data = ShelfMinRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    require_store_access(actor, data.store_id)
    row = godown_service.set_shelf_min(data, actor)
    level = None if row.shelf_min_qty is None else str(row.shelf_min_qty)
    return jsonify({"product_id": row.product_id, "shelf_min_qty": level}), 200


@inventory_bp.get("/inventory/refill")
@require_permission("inventory.read")
def refill():
    """Shelves at or below their refill level with stock waiting in the godown."""
    return jsonify([r.model_dump(mode="json") for r in godown_service.refill_list(_store_id_arg())]), 200


@inventory_bp.get("/inventory/transfers")
@require_permission("inventory.read")
def transfers():
    """Recent godown ↔ shelf moves (?product_id= for one product)."""
    product_id = request.args.get("product_id", type=int)
    rows = godown_service.recent_transfers(_store_id_arg(), product_id)
    return jsonify([r.model_dump(mode="json") for r in rows]), 200


@inventory_bp.get("/inventory/ledger")
@require_permission("inventory.read")
def ledger():
    product_id = request.args.get("product_id", type=int)
    txns = inventory_service.ledger(_store_id_arg(), product_id)
    return jsonify([InventoryTxnOut.model_validate(t).model_dump(mode="json") for t in txns]), 200
