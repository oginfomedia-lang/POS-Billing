"""Product queries, including find_by_barcode()."""
from app.models.product import Product
from app.repositories.base_repository import BaseRepository


class ProductRepository(BaseRepository):
    model = Product
