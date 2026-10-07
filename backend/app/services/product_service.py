"""Product, category and barcode management service layer."""
from decimal import Decimal

from app.errors.exceptions import BadRequestError, ConflictError, NotFoundError
from app.extensions import db
from app.models.category import Category
from app.models.enums import BarcodeType
from app.models.product import INHOUSE_BARCODE_SEQ, Product, ProductBarcode
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.product_schemas import (
    BarcodeCreatePayload,
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductUpdate,
)
from app.utils.barcode_utils import generate_inhouse_barcode, parse_variable_weight_barcode
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
) -> tuple[list[Product], int]:
    return ProductRepository().list(
        page=page, per_page=per_page,
        active_only=active_only, category_id=category_id, store_id=store_id,
        search=search.strip() if search else None,
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
        uom=data.uom,
        is_variable_weight=data.is_variable_weight,
        store_id=data.store_id,
    )

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
    if data.uom is not None:
        product.uom = data.uom

    if data.is_variable_weight is not None:
        product.is_variable_weight = data.is_variable_weight
    if data.is_active is not None:
        product.is_active = data.is_active
    if data.store_id is not None:
        product.store_id = data.store_id

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


def scan_barcode(scanned_value: str) -> dict:
    """Billing scanner lookup endpoint logic.

    Decodes variable-weight barcodes starting with '20' or performs standard product lookup.
    """
    code = scanned_value.strip()
    if not code:
        raise BadRequestError("Scanned barcode value cannot be empty.")

    # 1. Variable-weight check
    vw_data = parse_variable_weight_barcode(code)
    if vw_data:
        # Find product by SKU or barcode
        product = ProductRepository().find_by_sku(vw_data.sku)
        if not product:
            product = ProductRepository().find_by_barcode(code)

        if product:
            unit_price = Decimal(str(product.price))
            calculated_price = round(unit_price * Decimal(str(vw_data.weight_kg)), 2)
            inv = product.inventory
            qty = float(inv.qty_on_hand) if inv else None

            return {
                "product": product,
                "scanned_barcode": code,
                "is_variable_weight": True,
                "weight_grams": vw_data.weight_grams,
                "weight_kg": vw_data.weight_kg,
                "unit_price": unit_price,
                "calculated_price": calculated_price,
                "qty_on_hand": qty,
            }

    # 2. Standard Product Lookup
    product = ProductRepository().find_by_barcode(code)
    if not product:
        product = ProductRepository().find_by_sku(code)

    if not product:
        raise NotFoundError(f"No active product found for barcode '{code}'.")

    unit_price = Decimal(str(product.price))
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
