"""Product, category and barcode management service layer."""
from decimal import Decimal

from app.errors.exceptions import BadRequestError, ConflictError, NotFoundError
from app.extensions import db
from app.models.category import Category
from app.models.enums import BarcodeType
from app.models.product import INHOUSE_BARCODE_SEQ, Product, ProductBarcode
from app.models.supplier import Supplier
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.product_schemas import (
    BarcodeCreatePayload,
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductUpdate,
)
from app.services import inventory_service, settings_service
from app.utils.barcode_utils import generate_inhouse_barcode, parse_scale_barcode
from app.utils.money import round_money
from app.utils.transactions import transaction


# ── Categories ───────────────────────────────────────────────────────────────

def list_categories(active_only: bool = False) -> list[Category]:
    items, _ = CategoryRepository().list(per_page=1000, active_only=active_only)
    return items


def create_category(data: CategoryCreate) -> Category:
    repo = CategoryRepository()
    if repo.get_by_name(data.name):
        raise ConflictError(f"Category '{data.name}' already exists.")
    cat = Category(name=data.name, parent_id=data.parent_id)
    with transaction():
        repo.add(cat)
        db.session.flush()
    return cat


def update_category(category_id: int, data: CategoryUpdate) -> Category:
    cat = _get_category_or_404(category_id)
    if data.name is not None:
        cat.name = data.name
    if data.parent_id is not None:
        cat.parent_id = data.parent_id
    if data.is_active is not None:
        cat.is_active = data.is_active
    with transaction():
        pass
    return cat


# ── Products ──────────────────────────────────────────────────────────────────

def list_products(
    page: int = 1,
    per_page: int = 25,
    active_only: bool = False,
    category_id: int | None = None,
    store_id: int | None = None,
    search: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[Product], int]:
    return ProductRepository().list(
        page=page, per_page=per_page,
        active_only=active_only, category_id=category_id, store_id=store_id,
        search=search.strip() if search else None, is_active=is_active,
    )


def create_product(data: ProductCreate) -> Product:
    repo = ProductRepository()
    
    # Check SKU uniqueness if provided
    sku = data.sku.strip() if data.sku else None
    if sku:
        existing_sku = repo.find_by_sku(sku)
        if existing_sku:
            raise ConflictError(f"SKU '{sku}' already exists.")

    product = Product(
        sku=sku or "TEMP",
        name=data.name,
        description=data.description,
        category_id=data.category_id,
        price=data.price,
        tax_rate=data.tax_rate,
        mrp=data.mrp,
        hsn_code=data.hsn_code,
        uom=data.uom,
        is_variable_weight=data.is_variable_weight,
        plu_code=data.plu_code,
        store_id=data.store_id,
        supplier_id=data.supplier_id,
    )
    _check_mrp(product)
    _check_plu(product)
    _check_supplier(product.supplier_id)

    with transaction():
        repo.add(product)
        db.session.flush()
        if not sku:
            product.sku = f"SKU-{product.id:05d}"

        # Add barcodes
        for item in data.barcodes:
            if isinstance(item, str):
                b_str = item.strip()
                b_type = _infer_barcode_type(b_str)
                is_pri = False
            elif isinstance(item, BarcodeCreatePayload):
                b_str = item.barcode.strip()
                b_type = item.barcode_type
                is_pri = item.is_primary
            elif isinstance(item, dict):
                b_str = str(item.get("barcode", "")).strip()
                b_type = item.get("barcode_type", _infer_barcode_type(b_str))
                is_pri = bool(item.get("is_primary", False))
            else:
                continue

            if not b_str:
                continue

            _add_barcode_to_product(product, b_str, b_type, is_pri)

        # Mark first barcode as primary if none specified as primary
        if product.barcodes and not any(b.is_primary for b in product.barcodes):
            product.barcodes[0].is_primary = True

    return product


def update_product(product_id: int, data: ProductUpdate) -> Product:
    product = _get_product_or_404(product_id)

    if data.sku is not None:
        new_sku = data.sku.strip()
        if new_sku != product.sku:
            existing_sku = ProductRepository().find_by_sku(new_sku)
            if existing_sku and existing_sku.id != product.id:
                raise ConflictError(f"SKU '{new_sku}' is already assigned to another product.")
            product.sku = new_sku

    if data.name is not None:
        product.name = data.name
    if data.description is not None:
        product.description = data.description
    if data.category_id is not None:
        product.category_id = data.category_id
    if data.price is not None:
        product.price = data.price
    if data.tax_rate is not None:
        product.tax_rate = data.tax_rate
    # mrp / hsn_code can be cleared, so "sent" (even as null) means "set it".
    if "mrp" in data.model_fields_set:
        product.mrp = data.mrp
    if "hsn_code" in data.model_fields_set:
        product.hsn_code = data.hsn_code
    _check_mrp(product)
    if data.uom is not None:
        product.uom = data.uom

    if data.is_variable_weight is not None:
        product.is_variable_weight = data.is_variable_weight
    if "plu_code" in data.model_fields_set:
        product.plu_code = data.plu_code
    if not product.is_variable_weight:
        product.plu_code = None  # only loose items have a scale code
    _check_plu(product)
    if data.is_active is not None:
        product.is_active = data.is_active
    if data.store_id is not None:
        product.store_id = data.store_id
    if "supplier_id" in data.model_fields_set:  # null = no supplier
        _check_supplier(data.supplier_id)
        product.supplier_id = data.supplier_id

    with transaction():
        if data.barcodes is not None:
            # Sync barcodes
            existing_map = {b.barcode: b for b in product.barcodes}
            new_barcodes_set = set()

            for item in data.barcodes:
                if isinstance(item, str):
                    b_str = item.strip()
                    b_type = _infer_barcode_type(b_str)
                    is_pri = False
                elif isinstance(item, BarcodeCreatePayload):
                    b_str = item.barcode.strip()
                    b_type = item.barcode_type
                    is_pri = item.is_primary
                elif isinstance(item, dict):
                    b_str = str(item.get("barcode", "")).strip()
                    b_type = item.get("barcode_type", _infer_barcode_type(b_str))
                    is_pri = bool(item.get("is_primary", False))
                else:
                    continue

                if not b_str:
                    continue

                new_barcodes_set.add(b_str)
                if b_str not in existing_map:
                    _add_barcode_to_product(product, b_str, b_type, is_pri)
                else:
                    existing_map[b_str].barcode_type = b_type
                    if is_pri:
                        existing_map[b_str].is_primary = True

            # Remove omitted barcodes
            for b_str, pb in list(existing_map.items()):
                if b_str not in new_barcodes_set:
                    db.session.delete(pb)

    return product


def get_product(product_id: int) -> Product:
    return _get_product_or_404(product_id)


def add_product_barcode(
    product_id: int,
    barcode: str,
    barcode_type: BarcodeType | str = BarcodeType.MANUFACTURER,
    is_primary: bool = False,
) -> ProductBarcode:
    product = _get_product_or_404(product_id)
    barcode_str = barcode.strip()
    if not barcode_str:
        raise BadRequestError("Barcode string cannot be empty.")

    if isinstance(barcode_type, str):
        try:
            barcode_type = BarcodeType(barcode_type.upper())
        except ValueError:
            barcode_type = BarcodeType.MANUFACTURER

    with transaction():
        pb = _add_barcode_to_product(product, barcode_str, barcode_type, is_primary)
        db.session.flush()

    return pb


def remove_product_barcode(product_id: int, barcode_str: str) -> None:
    product = _get_product_or_404(product_id)
    barcode_str = barcode_str.strip()

    target = db.session.scalar(
        db.select(ProductBarcode)
        .where(ProductBarcode.product_id == product.id)
        .where(ProductBarcode.barcode == barcode_str)
    )
    if not target:
        raise NotFoundError(f"Barcode '{barcode_str}' not mapped to product {product_id}.")

    with transaction():
        db.session.delete(target)


MAX_INHOUSE_NUMBER = 999_999_999  # 9 digits fit between the 290 prefix and the check digit


def next_inhouse_barcode() -> str:
    """Returns a new, unused in-house EAN-13 code (290 + 9-digit sequence number + check digit).

    Works before the product exists (the Add Product form needs a code to show). Numbers
    already used by older codes are skipped, so it never collides with an existing barcode.
    """
    for _ in range(1000):
        number = db.session.scalar(db.select(INHOUSE_BARCODE_SEQ.next_value()))
        if number > MAX_INHOUSE_NUMBER:
            raise ConflictError("In-house barcode numbers are exhausted.")
        code = generate_inhouse_barcode(number)
        taken = db.session.scalar(db.select(ProductBarcode.id).where(ProductBarcode.barcode == code))
        if not taken:
            return code
    raise ConflictError("Could not find a free in-house barcode. Try again.")


def generate_and_save_inhouse_barcode(product_id: int) -> ProductBarcode:
    """Gives the product an in-house barcode. A product keeps one: asking again returns the same code."""
    product = _get_product_or_404(product_id)
    for pb in product.barcodes:
        if pb.barcode_type is BarcodeType.IN_HOUSE:
            return pb

    with transaction():
        pb = _add_barcode_to_product(product, next_inhouse_barcode(), BarcodeType.IN_HOUSE, is_primary=not product.barcodes)
        db.session.flush()
    return pb


def scan_barcode(scanned_value: str, store_id: int | None = None) -> dict:
    """Billing scanner lookup.

    A weighing-scale sticker (format set in Settings) finds the loose item by its scale code and carries
    the weight (or the price, converted to a weight). Anything else is a normal barcode or SKU lookup.
    store_id = the bill's store, for that store's own price.
    """
    code = scanned_value.strip()
    if not code:
        raise BadRequestError("Scanned barcode value cannot be empty.")

    scale = _scan_scale_sticker(code, store_id)
    if scale is not None:
        return scale

    product = ProductRepository().find_by_barcode(code)
    if not product:
        product = ProductRepository().find_by_sku(code)

    if not product:
        raise NotFoundError(f"No active product found for barcode '{code}'.")

    unit_price = _price_for(product, store_id)
    inv = product.inventory
    qty = float(inv.qty_on_hand) if inv else None

    return {
        "product": product,
        "scanned_barcode": code,
        "is_variable_weight": product.is_variable_weight,
        "weight_grams": None,
        "weight_kg": None,
        "unit_price": unit_price,
        "calculated_price": unit_price,
        "qty_on_hand": qty,
    }


def _scan_scale_sticker(code: str, store_id: int | None) -> dict | None:
    """None = not a scale sticker, or no loose item has that code (then it's tried as a normal barcode)."""
    s = settings_service.get_settings()
    parsed = parse_scale_barcode(code, s.scale_prefix, s.scale_plu_digits)
    if parsed is None:
        return None
    repo = ProductRepository()
    product = repo.find_by_plu(parsed.plu)
    if product is None:
        # Older setup: the scale code was the product's SKU.
        by_sku = repo.find_by_sku(code[2:2 + s.scale_plu_digits])  # as printed, e.g. '00123'
        product = by_sku if by_sku is not None and by_sku.is_variable_weight else None
    if product is None:
        # A real product barcode in the 20-28 range (rare) still scans normally.
        if ProductRepository().find_by_barcode(code) or ProductRepository().find_by_sku(code):
            return None
        raise NotFoundError(f"No loose item with scale code {parsed.plu}. Set it on the product (Scale item code).")
    if parsed.value <= 0:
        raise BadRequestError("The sticker shows 0 weight. Weigh the item again.")

    unit_price = _price_for(product, store_id)  # per kg, before GST
    if s.scale_value == "price":
        with_gst = unit_price * (1 + Decimal(product.tax_rate or 0) / 100)
        if with_gst <= 0:
            raise BadRequestError(f"{product.name} has no price; can't work out the weight from the sticker.")
        weight_kg = (Decimal(parsed.value) / 100 / with_gst).quantize(Decimal("0.001"))
        if weight_kg <= 0:
            raise BadRequestError("The sticker price is too small for this item.")
    else:
        weight_kg = (Decimal(parsed.value) / 1000).quantize(Decimal("0.001"))

    inv = product.inventory
    return {
        "product": product,
        "scanned_barcode": code,
        "is_variable_weight": True,
        "weight_grams": int(weight_kg * 1000),
        "weight_kg": float(weight_kg),
        "unit_price": unit_price,
        "calculated_price": round_money(unit_price * weight_kg),
        "qty_on_hand": float(inv.qty_on_hand) if inv else None,
    }


def _price_for(product: Product, store_id: int | None) -> Decimal:
    return inventory_service.selling_price(store_id, product) if store_id else Decimal(str(product.price))


def get_by_barcode(barcode: str) -> Product:
    product = ProductRepository().find_by_barcode(barcode)
    if product is None:
        # Fallback SKU match
        product = ProductRepository().find_by_sku(barcode)
    if product is None:
        raise NotFoundError(f"No active product found for barcode '{barcode}'.")
    return product


# ── Helpers ───────────────────────────────────────────────────────────────────

def _add_barcode_to_product(
    product: Product, barcode_str: str, barcode_type: BarcodeType, is_primary: bool
) -> ProductBarcode:
    existing = db.session.scalar(
        db.select(ProductBarcode).where(ProductBarcode.barcode == barcode_str)
    )
    if existing:
        raise ConflictError(f"Barcode '{barcode_str}' is already assigned to a product.")

    pb = ProductBarcode(
        product_id=product.id,
        barcode=barcode_str,
        barcode_type=barcode_type,
        is_primary=is_primary,
    )
    db.session.add(pb)
    product.barcodes.append(pb)
    return pb



def _infer_barcode_type(barcode_str: str) -> BarcodeType:
    if barcode_str.startswith("290") and len(barcode_str) == 13:
        return BarcodeType.IN_HOUSE
    if barcode_str.startswith("20") and len(barcode_str) == 13:
        return BarcodeType.PRICE_EMBEDDED
    return BarcodeType.MANUFACTURER


def _get_product_or_404(product_id: int) -> Product:
    p = ProductRepository().get_by_id(product_id)
    if p is None:
        raise NotFoundError(f"Product {product_id} not found.")
    return p


def _get_category_or_404(category_id: int) -> Category:
    c = CategoryRepository().get_by_id(category_id)
    if c is None:
        raise NotFoundError(f"Category {category_id} not found.")
    return c


def mrp_error(price, tax_rate, mrp) -> str | None:
    """MRP includes GST, so it can't be below our price + GST (that would be selling above MRP — illegal)."""
    if mrp is None:
        return None
    with_gst = round_money(Decimal(price) * (1 + Decimal(tax_rate or 0) / 100))
    if Decimal(mrp) < with_gst:
        return f"MRP (₹{mrp}) can't be lower than the selling price with GST (₹{with_gst})."
    return None


def _check_mrp(product: Product) -> None:
    error = mrp_error(product.price, product.tax_rate, product.mrp)
    if error:
        db.session.rollback()  # undo the in-memory edits on an existing product
        raise BadRequestError(error)


def _check_supplier(supplier_id: int | None) -> None:
    if supplier_id is None:
        return
    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None or not supplier.is_active:
        db.session.rollback()
        raise BadRequestError("Choose an active supplier.")


def _check_plu(product: Product) -> None:
    """Only loose items have a scale code, and each code belongs to one product."""
    if product.plu_code is None:
        return
    if not product.is_variable_weight:
        db.session.rollback()
        raise BadRequestError("Only loose (weighed) items can have a scale item code.")
    with db.session.no_autoflush:  # don't write the edited product before the check
        other = db.session.scalar(
            db.select(Product).where(Product.plu_code == product.plu_code, Product.id != product.id)
        )
    if other is not None:
        db.session.rollback()
        raise ConflictError(f"Scale item code {product.plu_code} is already used by '{other.name}'.")
