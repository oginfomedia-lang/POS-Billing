"""Product and barcode endpoints, GET /products/barcode/<barcode>."""
from flask import Blueprint, jsonify, request

from app.schemas.common import PagedResponse, PaginationQuery
from app.schemas.product_schemas import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    ProductBarcodeOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from app.services import product_service
from app.utils.permissions import require_permission

product_bp = Blueprint("products", __name__)


# ── Categories ────────────────────────────────────────────────────────────────

@product_bp.get("/categories")
@require_permission("categories.read")
def list_categories():
    active_only = request.args.get("active_only", "false").lower() == "true"
    items = product_service.list_categories(active_only=active_only)
    return jsonify([CategoryOut.model_validate(c).model_dump(mode="json") for c in items]), 200


@product_bp.post("/categories")
@require_permission("categories.create")
def create_category():
    data = CategoryCreate.model_validate(request.get_json(force=True))
    cat = product_service.create_category(data)
    return jsonify(CategoryOut.model_validate(cat).model_dump(mode="json")), 201


@product_bp.put("/categories/<int:category_id>")
@require_permission("categories.update")
def update_category(category_id: int):
    data = CategoryUpdate.model_validate(request.get_json(force=True))
    cat = product_service.update_category(category_id, data)
    return jsonify(CategoryOut.model_validate(cat).model_dump(mode="json")), 200


# ── Products ──────────────────────────────────────────────────────────────────

@product_bp.get("/products")
@require_permission("products.read")
def list_products():
    q = PaginationQuery.model_validate(request.args)
    active_only = request.args.get("active_only", "false").lower() == "true"
    category_id = request.args.get("category_id", type=int)
    store_id = request.args.get("store_id", type=int)
    items, total = product_service.list_products(
        page=q.page, per_page=q.per_page,
        active_only=active_only, category_id=category_id, store_id=store_id,
    )
    resp = PagedResponse.build(
        [ProductOut.model_validate(p).model_dump(mode="json") for p in items],
        total, q.page, q.per_page,
    )
    return jsonify(resp.model_dump()), 200


@product_bp.post("/products")
@require_permission("products.create")
def create_product():
    data = ProductCreate.model_validate(request.get_json(force=True))
    product = product_service.create_product(data)
    return jsonify(ProductOut.model_validate(product).model_dump(mode="json")), 201


@product_bp.get("/products/<int:product_id>")
@require_permission("products.read")
def get_product(product_id: int):
    product = product_service.get_product(product_id)
    return jsonify(ProductOut.model_validate(product).model_dump(mode="json")), 200


@product_bp.put("/products/<int:product_id>")
@require_permission("products.update")
def update_product(product_id: int):
    data = ProductUpdate.model_validate(request.get_json(force=True))
    product = product_service.update_product(product_id, data)
    return jsonify(ProductOut.model_validate(product).model_dump(mode="json")), 200


@product_bp.get("/products/barcode/<string:barcode>")
@require_permission("products.read")
def get_by_barcode(barcode: str):
    product = product_service.get_by_barcode(barcode)
    inventory = product.inventory
    qty = float(inventory.qty_on_hand) if inventory else None
    resp = ProductBarcodeOut(product=ProductOut.model_validate(product), qty_on_hand=qty)
    return jsonify(resp.model_dump(mode="json")), 200
