"""Product and ProductBarcode models (one product, many barcodes)."""
from app.extensions import db
from app.models.base import TimestampMixin


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True)

    category = db.relationship("Category", back_populates="products")
    store = db.relationship("Store")
    barcodes = db.relationship("ProductBarcode", back_populates="product", cascade="all, delete-orphan")
    inventory = db.relationship("Inventory", back_populates="product", uselist=False)

    def __repr__(self) -> str:
        return f"<Product {self.name}>"


class ProductBarcode(db.Model):
    __tablename__ = "product_barcodes"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    barcode = db.Column(db.String(100), unique=True, nullable=False, index=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)

    product = db.relationship("Product", back_populates="barcodes")

    def __repr__(self) -> str:
        return f"<ProductBarcode {self.barcode}>"
