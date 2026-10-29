"""Product, category and barcode management service layer."""
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app.errors.exceptions import BadRequestError, ConflictError, NotFoundError
from app.extensions import db
from app.models.category import Category
from app.models.enums import BarcodeType
from app.models.product import INHOUSE_BARCODE_SEQ, Product, ProductBarcode
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.product_schemas import (
    BarcodeCreatePayload,
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductUpdate,
)
from app.services import inventory_service, settings_service, sku_service
from app.utils.barcode_utils import generate_inhouse_barcode, parse_scale_barcode
from app.utils.money import round_money
from app.utils.transactions import transaction


# ── Categories ───────────────────────────────────────────────────────────────

def list_categories(active_only: bool = False) -> list[Category]:
    items, _ = CategoryRepository().list(per_page=1000, active_only=active_only)
    return items


def create_category(data: CategoryCreate) -> Category:
    repo = CategoryRepository()
    _check_category_name_free(data.name)
    if data.parent_id is not None:
        _get_category_or_404(data.parent_id)
    cat = Category(name=data.name, parent_id=data.parent_id)
    with transaction():
        repo.add(cat)
        db.session.flush()
    return cat


def update_category(category_id: int, data: CategoryUpdate) -> Category:
    cat = _get_category_or_404(category_id)
    sent = data.model_fields_set
    if data.name is not None and data.name != cat.name:
        _check_category_name_free(data.name, except_id=cat.id)
        cat.name = data.name
    if "parent_id" in sent:
        _check_parent(cat, data.parent_id)
        cat.parent_id = data.parent_id
    if data.is_active is not None:
        cat.is_active = data.is_active
    with transaction():
        pass
    return cat


def delete_category(category_id: int) -> None:
    """Only an unused category can be deleted; one in use can be deactivated instead (history stays intact)."""
    cat = _get_category_or_404(category_id)
    from app.models.discount import Discount

    in_use = [
        (db.session.scalar(db.select(db.func.count()).select_from(Product).where(Product.category_id == cat.id)), "product"),
        (db.session.scalar(db.select(db.func.count()).select_from(Category).where(Category.parent_id == cat.id)), "sub-category"),
        (db.session.scalar(db.select(db.func.count()).select_from(Discount).where(Discount.category_id == cat.id)), "offer"),
    ]
    used = [f"{n} {what}{'s' if n != 1 else ''}" for n, what in in_use if n]
    if used:
        raise ConflictError(
            f"Category '{cat.name}' is used by {', '.join(used)}, so it can't be deleted. "
            "Move them to another category first, or deactivate this category instead."
        )
    with transaction():
        db.session.delete(cat)


def _check_category_name_free(name: str, except_id: int | None = None) -> None:
    existing = CategoryRepository().get_by_name_ci(name)
    if existing is not None and existing.id != except_id:
        raise ConflictError(f"Category '{existing.name}' already exists.")


def _check_parent(cat: Category, parent_id: int | None) -> None:
    """A category can't sit under itself or under one of its own sub-categories."""
    if parent_id is None:
        return
    _get_category_or_404(parent_id)
    parents = CategoryRepository().parent_map()
    node: int | None = parent_id
    while node is not None:
        if node == cat.id:
            raise BadRequestError("A category can't be placed under itself or one of its own sub-categories.")
        node = parents.get(node)


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
    """No SKU given: one is made from the category and the name (KIR-SAK-0001, app/services/sku_service.py)."""
    repo = ProductRepository()

    # Check SKU uniqueness if provided
    sku = data.sku.strip() if data.sku else None
    if sku:
        existing_sku = repo.find_by_sku(sku)
        if existing_sku:
            raise ConflictError(f"SKU '{sku}' already exists.")

    product = Product(
        sku=sku or sku_service.generate(data.category_id, data.name),
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
        cost_price=data.cost_price,
    )
    _check_mrp(product)
    _check_plu(product)
    _check_supplier(product.supplier_id)

    try:
        with transaction():
            repo.add(product)
            db.session.flush()
            link_supplier(product)

            wanted = _wanted_barcode(data.barcodes)
            if wanted:
                _add_barcode_to_product(product, *wanted)
    except IntegrityError as exc:
        # The same SKU saved by someone else a moment ago (only possible for one typed by hand): nothing was
        # saved, say so instead of failing with a server error.
        if "uq_products_sku" in str(exc.orig):
            raise ConflictError(f"SKU '{product.sku}' already exists.") from exc
        raise

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
    if "cost_price" in data.model_fields_set:
        product.cost_price = data.cost_price
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
        link_supplier(product)
        if data.barcodes is not None:
            # The product ends up with exactly the barcode sent (or none). The old one goes first, so a
            # barcode can be replaced in one save.
            wanted = _wanted_barcode(data.barcodes)
            for pb in list(product.barcodes):
                if wanted and pb.barcode == wanted[0]:
                    pb.barcode_type = wanted[1]
                else:
                    product.barcodes.remove(pb)
                    db.session.delete(pb)
            db.session.flush()
            if wanted and not product.barcodes:
                _add_barcode_to_product(product, *wanted)

    return product


def get_product(product_id: int) -> Product:
    return _get_product_or_404(product_id)


def add_product_barcode(
    product_id: int,
    barcode: str,
    barcode_type: BarcodeType | str = BarcodeType.MANUFACTURER,
    is_primary: bool = False,
) -> ProductBarcode:
    """Gives a product its barcode. A product has at most one: remove the old one first."""
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
        pb = _add_barcode_to_product(product, barcode_str, barcode_type)
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
    """Gives the product an in-house barcode. Asking again returns the same code. A product that already has
    another barcode is refused (one barcode per product)."""
    product = _get_product_or_404(product_id)
    for pb in product.barcodes:
        if pb.barcode_type is BarcodeType.IN_HOUSE:
            return pb

    with transaction():
        pb = _add_barcode_to_product(product, next_inhouse_barcode(), BarcodeType.IN_HOUSE)
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

def _add_barcode_to_product(product: Product, barcode_str: str, barcode_type: BarcodeType) -> ProductBarcode:
    """One barcode per product (also a unique index on product_barcodes.product_id)."""
    if product.barcodes:
        raise ConflictError(
            f"'{product.name}' already has barcode {product.barcodes[0].barcode}. "
            "A product can have only one barcode: remove it first."
        )
    existing = db.session.scalar(
        db.select(ProductBarcode).where(ProductBarcode.barcode == barcode_str)
    )
    if existing:
        raise ConflictError(f"Barcode '{barcode_str}' is already assigned to a product.")

    pb = ProductBarcode(
        product_id=product.id,
        barcode=barcode_str,
        barcode_type=barcode_type,
        is_primary=True,
    )
    db.session.add(pb)
    product.barcodes.append(pb)
    return pb



def _wanted_barcode(items: list) -> tuple[str, BarcodeType] | None:
    """The (barcode, type) a create / update asks for, or None. The schemas allow at most one."""
    for item in items:
        if isinstance(item, BarcodeCreatePayload):
            b_str, b_type = item.barcode.strip(), item.barcode_type
        else:
            b_str = str(item).strip()
            b_type = _infer_barcode_type(b_str)
        if b_str:
            return b_str, b_type
    return None


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


def link_supplier(product: Product) -> None:
    """The product's usual supplier also gets it in their product list (Suppliers → products), so it shows
    on the supplier's page and in their purchase orders. Purchase prices there are left as they are."""
    if product.supplier_id is None or product.id is None:
        return
    link = db.session.scalar(
        db.select(SupplierProduct).where(
            SupplierProduct.supplier_id == product.supplier_id, SupplierProduct.product_id == product.id
        )
    )
    if link is None:
        has_preferred = db.session.scalar(
            db.select(SupplierProduct.id).where(
                SupplierProduct.product_id == product.id, SupplierProduct.is_preferred.is_(True)
            )
        )
        db.session.add(SupplierProduct(
            supplier_id=product.supplier_id, product_id=product.id, is_preferred=has_preferred is None,
        ))
    elif not link.is_active:
        link.is_active = True


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
