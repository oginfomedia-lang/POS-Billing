"""A supplier's bill layout: where each column is, saved the last time their bill's table header was read.

Used when a later bill's header can't be read (blurred photo, cut off): the columns are taken from here.
"""
from app.extensions import db
from app.models.base import TimestampMixin


class SupplierBillTemplate(TimestampMixin, db.Model):
    __tablename__ = "supplier_bill_templates"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    # [{"field": "qty", "x0": 0.41, "x1": 0.47}, ...]: each column's left/right edge as a share of the page width
    columns = db.Column(db.JSON, nullable=False)
    times_used = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint("supplier_id", name="uq_supplier_bill_templates_supplier"),)

    supplier = db.relationship("Supplier")

    def __repr__(self) -> str:
        return f"<SupplierBillTemplate supplier={self.supplier_id}>"