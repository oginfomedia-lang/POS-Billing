"""SupplierProduct: maps a product to one or more suppliers with purchase-specific details."""
from app.extensions import db
from app.models.base import TimestampMixin


class SupplierProduct(TimestampMixin, db.Model):
    __tablename__ = "supplier_products"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(
        db.Integer, db.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_product_code = db.Column(db.String(100), nullable=True)
    purchase_price = db.Column(db.Numeric(12, 2), nullable=True)
    last_purchase_price = db.Column(db.Numeric(12, 2), nullable=True)
    min_order_qty = db.Column(db.Numeric(12, 3), nullable=True)
    lead_time_days = db.Column(db.Integer, nullable=True)
    is_preferred = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.UniqueConstraint("supplier_id", "product_id", name="uq_supplier_products_supplier_product"),
    )

    supplier = db.relationship("Supplier", back_populates="supplier_products")
    product = db.relationship("Product")

    def __repr__(self) -> str:
        return f"<SupplierProduct supplier={self.supplier_id} product={self.product_id}>"
