"""What a supplier calls a product on their bill → our product.

Learnt when a Direct purchase read from the bill (OCR) is saved, so their next bill matches by itself, even
when the bill says "TATA SALT 1KG" and the product is "टाटा मीठ 1 किलो".
"""
from app.extensions import db
from app.models.base import TimestampMixin


class SupplierItemAlias(TimestampMixin, db.Model):
    __tablename__ = "supplier_item_aliases"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(
        db.Integer, db.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # search_key() of the bill's text (app/utils/search_key.py): spaces, case and vowel misreads don't matter.
    description_key = db.Column(db.String(400), nullable=False)
    description = db.Column(db.String(300), nullable=False)  # as last printed on the bill, for people
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    times_used = db.Column(db.Integer, nullable=False, default=1)

    __table_args__ = (
        db.UniqueConstraint("supplier_id", "description_key", name="uq_supplier_item_aliases_supplier_key"),
    )

    supplier = db.relationship("Supplier")
    product = db.relationship("Product")

    def __repr__(self) -> str:
        return f"<SupplierItemAlias {self.description!r} → product {self.product_id}>"