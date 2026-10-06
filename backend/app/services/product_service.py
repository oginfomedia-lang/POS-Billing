"""Product, category and barcode management; get_by_barcode()."""
from app.errors.exceptions import ConflictError, NotFoundError
from app.extensions import db
from app.models.product import Product, ProductBarcode
from app.models.category import Category
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.product_schemas import CategoryCreate, CategoryUpdate, ProductCreate, ProductUpdate
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
) -> tuple[list[Product], int]:
    return ProductRepository().list(
        page=page, per_page=per_page,
        active_only=active_only, category_id=category_id, store_id=store_id,
    )


def create_product(data: ProductCreate) -> Product:
    repo = ProductRepository()
    product = Product(
        name=data.name,
        description=data.description,
        category_id=data.category_id,
        price=data.price,
        tax_rate=data.tax_rate,
        store_id=data.store_id,
    )
    with transaction():
        repo.add(product)
        db.session.flush()
        for barcode_str in data.barcodes:
            barcode_str = barcode_str.strip()
            if not barcode_str:
                continue
            existing = db.session.scalar(
                db.select(ProductBarcode).where(ProductBarcode.barcode == barcode_str)
            )
            if existing:
                raise ConflictError(f"Barcode '{barcode_str}' already assigned to another product.")
            pb = ProductBarcode(product_id=product.id, barcode=barcode_str, is_primary=False)
            db.session.add(pb)
        # mark first barcode as primary
        if product.barcodes:
            product.barcodes[0].is_primary = True
    return product


def update_product(product_id: int, data: ProductUpdate) -> Product:
    product = _get_product_or_404(product_id)
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
    if data.is_active is not None:
        product.is_active = data.is_active
    if data.store_id is not None:
        product.store_id = data.store_id
    with transaction():
        pass
    return product


def get_product(product_id: int) -> Product:
    return _get_product_or_404(product_id)


def get_by_barcode(barcode: str) -> Product:
    product = ProductRepository().find_by_barcode(barcode)
    if product is None:
        raise NotFoundError(f"No active product found for barcode '{barcode}'.")
    return product


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
