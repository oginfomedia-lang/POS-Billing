"""Product and barcode management API routes."""
import io

from flask import Blueprint, jsonify, request, send_file

from app.errors.exceptions import BadRequestError
from app.schemas.common import PagedResponse, PaginationQuery
from app.schemas.product_schemas import (
    BarcodeOut,
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    ProductBarcodeOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from app.schemas.product_import_schemas import ImportOptions
from app.services import auth_service, inventory_service, product_import_service, product_service
from app.utils.permissions import require_permission
from app.utils.store_scope import require_store_access, scoped_store_id

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
    # Shared catalogue + this store's own products; branch users always see their own store.
    store_id = scoped_store_id(auth_service.current_user(), request.args.get("store_id", type=int))
    items, total = product_service.list_products(
        page=q.page, per_page=q.per_page,
        active_only=active_only, category_id=category_id, store_id=store_id,
        search=request.args.get("q"), is_active=q.is_active,
    )
    resp = PagedResponse.build(_with_store_prices(items, store_id), total, q.page, q.per_page)
    return jsonify(resp.model_dump()), 200


def _with_store_prices(products: list, store_id: int | None) -> list[dict]:
    """ProductOut dicts, with store_price filled in when a store is selected."""
    overrides = inventory_service.store_prices(store_id, [p.id for p in products]) if store_id else {}
    out = []
    for p in products:
        item = ProductOut.model_validate(p)
        item.store_price = overrides.get(p.id)
        out.append(item.model_dump(mode="json"))
    return out


@product_bp.post("/products")
@require_permission("products.create")
def create_product():
    data = ProductCreate.model_validate(request.get_json(force=True))
    product = product_service.create_product(data)
    return jsonify(ProductOut.model_validate(product).model_dump(mode="json")), 201


# ── Bulk import (CSV / Excel) ────────────────────────────────────────────────

@product_bp.get("/products/import/template")
@require_permission("products.create")
def import_template():
    return send_file(
        io.BytesIO(product_import_service.template_xlsx()),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="product-import-template.xlsx",
    )


def _import_request():
    """The uploaded file (multipart 'file') and the import-screen options (form fields)."""
    upload = request.files.get("file")
    if upload is None:
        raise BadRequestError("Choose a .csv or .xlsx file.")
    form = request.form
    options = ImportOptions(
        store_id=form.get("store_id", type=int),
        sold_in=form.get("sold_in") or "all",
        generate_barcodes=(form.get("generate_barcodes", "true").lower() == "true"),
    )
    rows, warnings = product_import_service.read_rows(upload.filename or "", upload.read())
    return upload.filename or "", rows, warnings, options


@product_bp.post("/products/import/preview")
@require_permission("products.create")
def import_preview():
    """Checks every row of the file and says what would happen. Saves nothing."""
    _, rows, warnings, options = _import_request()
    preview, _ = product_import_service.analyse(rows, options, auth_service.current_user())
    preview.warnings = warnings + preview.warnings
    return jsonify(preview.model_dump(mode="json")), 200


@product_bp.post("/products/import")
@require_permission("products.create")
def import_products():
    """Saves the file only if no row has an error (all or nothing); otherwise 400 with the preview."""
    filename, rows, warnings, options = _import_request()
    actor = auth_service.current_user()
    preview, parsed = product_import_service.analyse(rows, options, actor)
    if preview.errors:
        preview.warnings = warnings + preview.warnings
        return jsonify({
            "error": {"code": "IMPORT_HAS_ERRORS", "message": f"{preview.errors} row(s) have errors. Nothing was imported."},
            "preview": preview.model_dump(mode="json"),
        }), 400
    result = product_import_service.apply(parsed, options, actor, filename)
    return jsonify(result.model_dump(mode="json")), 201


@product_bp.get("/products/<int:product_id>")
@require_permission("products.read")
def get_product(product_id: int):
    store_id = scoped_store_id(auth_service.current_user(), request.args.get("store_id", type=int))
    product = product_service.get_product(product_id)
    if product.store_id is not None and store_id is not None and product.store_id != store_id:
        require_store_access(auth_service.current_user(), product.store_id)
    return jsonify(_with_store_prices([product], store_id)[0]), 200


@product_bp.put("/products/<int:product_id>")
@require_permission("products.update")
def update_product(product_id: int):
    # Branch managers may edit shared products and their own store's, not another store's.
    existing = product_service.get_product(product_id)
    if existing.store_id is not None:
        require_store_access(auth_service.current_user(), existing.store_id)
    data = ProductUpdate.model_validate(request.get_json(force=True))
    product = product_service.update_product(product_id, data)
    return jsonify(ProductOut.model_validate(product).model_dump(mode="json")), 200


# ── Barcodes & POS Scanner ───────────────────────────────────────────────────

@product_bp.post("/products/<int:id>/barcodes")
@require_permission("products.update")
def add_product_barcode(id: int):
    body = request.get_json(force=True) or {}
    barcode_str = body.get("barcode", "")
    barcode_type = body.get("barcode_type", "MANUFACTURER")
    is_primary = bool(body.get("is_primary", False))
    pb = product_service.add_product_barcode(id, barcode_str, barcode_type, is_primary)
    return jsonify(BarcodeOut.model_validate(pb).model_dump(mode="json")), 201


@product_bp.delete("/products/<int:id>/barcodes/<string:barcode>")
@require_permission("products.update")
def remove_product_barcode(id: int, barcode: str):
    product_service.remove_product_barcode(id, barcode)
    return jsonify({"message": f"Barcode '{barcode}' removed."}), 200


@product_bp.post("/products/barcodes/generate")
@require_permission("products.create")
def generate_new_inhouse_barcode():
    """A fresh unused in-house code, for the Add Product form (the product doesn't exist yet)."""
    return jsonify({"barcode": product_service.next_inhouse_barcode(), "barcode_type": "IN_HOUSE"}), 200


@product_bp.post("/products/<int:id>/generate-inhouse-barcode")
@require_permission("products.update")
def generate_inhouse_barcode_route(id: int):
    pb = product_service.generate_and_save_inhouse_barcode(id)
    return jsonify(BarcodeOut.model_validate(pb).model_dump(mode="json")), 201


@product_bp.get("/pos/scan")
@product_bp.get("/products/scan")
@require_permission("products.read")
def pos_scan_barcode():
    scanned_val = request.args.get("barcode") or request.args.get("code") or ""
    # store_id = the bill's store: loose-item stickers in price mode use that store's own price.
    res = product_service.scan_barcode(scanned_val, request.args.get("store_id", type=int))
    resp = ProductBarcodeOut(
        product=ProductOut.model_validate(res["product"]),
        scanned_barcode=res["scanned_barcode"],
        is_variable_weight=res["is_variable_weight"],
        weight_grams=res["weight_grams"],
        weight_kg=res["weight_kg"],
        unit_price=res["unit_price"],
        calculated_price=res["calculated_price"],
        qty_on_hand=res["qty_on_hand"],
    )
    return jsonify(resp.model_dump(mode="json")), 200


@product_bp.get("/products/barcode/<string:barcode>")
@require_permission("products.read")
def get_by_barcode(barcode: str):
    res = product_service.scan_barcode(barcode, request.args.get("store_id", type=int))
    resp = ProductBarcodeOut(
        product=ProductOut.model_validate(res["product"]),
        scanned_barcode=res["scanned_barcode"],
        is_variable_weight=res["is_variable_weight"],
        weight_grams=res["weight_grams"],
        weight_kg=res["weight_kg"],
        unit_price=res["unit_price"],
        calculated_price=res["calculated_price"],
        qty_on_hand=res["qty_on_hand"],
    )
    return jsonify(resp.model_dump(mode="json")), 200
