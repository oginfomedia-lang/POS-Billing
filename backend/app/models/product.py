import uuid

from app.extensions import db
from app.models.base import TimestampMixin, _now
from app.models.enums import BarcodeType, UOMType


# Numbers for in-house barcodes (290 + 9 digits + check digit). A sequence never hands out
# the same number twice, even under concurrent requests or for products not saved yet.
INHOUSE_BARCODE_SEQ = db.Sequence("inhouse_barcode_seq", metadata=db.metadata)


def _gen_sku() -> str:
    return f"SKU-{uuid.uuid4().hex[:8]}"


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False, default=_gen_sku)

    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    price = db.Column(db.Numeric(12, 2), nullable=False)  # selling price, before GST
    # Default purchase cost, before GST (for the profit report). Each store's GRNs keep inventory.avg_cost.
    cost_price = db.Column(db.Numeric(12, 4), nullable=True)
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    mrp = db.Column(db.Numeric(12, 2), nullable=True)  # printed MRP, incl. GST (per unit, or per kg if weighed)
    hsn_code = db.Column(db.String(8), nullable=True)  # GST HSN code, 4-8 digits
    uom = db.Column(db.Enum(UOMType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=UOMType.PCS)
    is_variable_weight = db.Column(db.Boolean, nullable=False, default=False)
    # Loose items: the item code set on the weighing scale (no leading zeros). Its barcode stickers carry it.
    plu_code = db.Column(db.String(6), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=True)

    category = db.relationship("Category", back_populates="products")
    store = db.relationship("Store")
    supplier = db.relationship("Supplier", back_populates="products", foreign_keys=[supplier_id])
    barcodes = db.relationship("ProductBarcode", back_populates="product", cascade="all, delete-orphan")
    inventory = db.relationship("Inventory", back_populates="product", uselist=False)

    __table_args__ = (
        db.Index("uq_products_plu_code", "plu_code", unique=True, postgresql_where=plu_code.isnot(None)),
    )

    def __repr__(self) -> str:
        return f"<Product {self.name}>"


class ProductBarcode(db.Model):
    __tablename__ = "product_barcodes"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    barcode = db.Column(db.String(100), unique=True, nullable=False, index=True)
    barcode_type = db.Column(db.Enum(BarcodeType), nullable=False, default=BarcodeType.MANUFACTURER)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)

    product = db.relationship("Product", back_populates="barcodes")

    def __repr__(self) -> str:
        return f"<ProductBarcode {self.barcode} ({self.barcode_type})>"

