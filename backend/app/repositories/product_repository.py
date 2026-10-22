"""Product queries, including find_by_barcode()."""
from app.extensions import db
from app.models.product import Product, ProductBarcode
from app.repositories.base_repository import BaseRepository
from app.utils.search_key import MIN_QUERY_KEY, search_key


class ProductRepository(BaseRepository):
    model = Product

    def find_by_barcode(self, barcode: str) -> Product | None:
        return db.session.scalar(
            db.select(Product)
            .join(ProductBarcode, ProductBarcode.product_id == Product.id)
            .where(ProductBarcode.barcode == barcode)
            .where(Product.is_active.is_(True))
        )

    def find_by_plu(self, plu: str) -> Product | None:
        """Active loose item with this weighing-scale code (stored without leading zeros)."""
        return db.session.scalar(
            db.select(Product)
            .where(Product.plu_code == plu)
            .where(Product.is_variable_weight.is_(True))
            .where(Product.is_active.is_(True))
        )

    def find_by_sku(self, sku: str) -> Product | None:
        sku = str(sku).strip()
        if not sku:
            return None

        # Try exact SKU match first
        product = db.session.scalar(
            db.select(Product)
            .where(Product.sku == sku)
            .where(Product.is_active.is_(True))
        )
        if product:
            return product

        # Try numeric matching or stripping leading zeroes (e.g. '00123' matching '123' or 'SKU-123')
        if sku.isdigit():
            numeric_val = str(int(sku))
            product = db.session.scalar(
                db.select(Product)
                .where((Product.sku == numeric_val) | (Product.sku == f"SKU-{numeric_val}"))
                .where(Product.is_active.is_(True))
            )

        return product


    def list(
        self,
        page: int = 1,
        per_page: int = 25,
        active_only: bool = False,
        category_id: int | None = None,
        store_id: int | None = None,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Product], int]:
        q = db.select(Product)
        if is_active is not None:
            q = q.where(Product.is_active.is_(is_active))
        if search:
            # Name / SKU contains the text, or an exact barcode match, or the name sounds like it:
            # "madhur" finds "मधुर साखर", "tandul" finds "Tandool" (app/utils/search_key.py).
            # % and _ typed in the box are ordinary characters, not wildcards (autoescape).
            by_barcode = db.select(ProductBarcode.product_id).where(ProductBarcode.barcode == search)
            match = (Product.name.icontains(search, autoescape=True) | Product.sku.icontains(search, autoescape=True)
                     | Product.id.in_(by_barcode))
            key = search_key(search)
            if len(key) >= MIN_QUERY_KEY:
                match = match | Product.search_key.contains(key, autoescape=True)
            q = q.where(match)
        if active_only:
            q = q.where(Product.is_active.is_(True))
        if category_id is not None:
            q = q.where(Product.category_id == category_id)
        if store_id is not None:
            q = q.where((Product.store_id == store_id) | (Product.store_id.is_(None)))
        total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery()))
        items = db.session.scalars(
            q.order_by(Product.name).offset((page - 1) * per_page).limit(per_page)
        ).all()
        return list(items), total or 0
