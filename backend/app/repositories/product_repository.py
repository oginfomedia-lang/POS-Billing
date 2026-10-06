"""Product queries, including find_by_barcode()."""
from app.extensions import db
from app.models.product import Product, ProductBarcode
from app.repositories.base_repository import BaseRepository


class ProductRepository(BaseRepository):
    model = Product

    def find_by_barcode(self, barcode: str) -> Product | None:
        return db.session.scalar(
            db.select(Product)
            .join(ProductBarcode, ProductBarcode.product_id == Product.id)
            .where(ProductBarcode.barcode == barcode)
            .where(Product.is_active.is_(True))
        )

    def list(
        self,
        page: int = 1,
        per_page: int = 25,
        active_only: bool = False,
        category_id: int | None = None,
        store_id: int | None = None,
    ) -> tuple[list[Product], int]:
        q = db.select(Product)
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
