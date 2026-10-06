"""Inventory (stock per store+product, CHECK qty >= 0) and InventoryTransaction (stock ledger)."""
from app.extensions import db
from app.models.base import TimestampMixin


class Inventory(TimestampMixin, db.Model):
    __tablename__ = "inventory"
    __table_args__ = (
        db.UniqueConstraint("store_id", "product_id", name="uq_inventory_store_id_product_id"),
        db.CheckConstraint("qty_on_hand >= 0", name="qty_non_negative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    qty_on_hand = db.Column(db.Integer, nullable=False, default=0)

    product = db.relationship("Product")

    def __repr__(self) -> str:
        return f"<Inventory store={self.store_id} product={self.product_id} qty={self.qty_on_hand}>"
