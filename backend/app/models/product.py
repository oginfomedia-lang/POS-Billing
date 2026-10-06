"""Product and ProductBarcode models (one product, many barcodes)."""
from app.extensions import db
from app.models.base import TimestampMixin


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    selling_price = db.Column(db.Numeric(12, 2), nullable=False)
    gst_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)  # percent, tax-exclusive
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    barcodes = db.relationship("ProductBarcode", back_populates="product", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Product {self.name}>"


class ProductBarcode(TimestampMixin, db.Model):
    __tablename__ = "product_barcodes"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    barcode = db.Column(db.String(64), unique=True, nullable=False)

    product = db.relationship("Product", back_populates="barcodes")

    def __repr__(self) -> str:
        return f"<ProductBarcode {self.barcode}>"
