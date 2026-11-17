"""SupplierReturn: goods sent back to the supplier after they were stocked (expired, damaged, recalled)."""
from app.extensions import db
from app.models.base import TimestampMixin


class SupplierReturn(TimestampMixin, db.Model):
    __tablename__ = "supplier_returns"

    id = db.Column(db.Integer, primary_key=True)
    return_number = db.Column(db.String(40), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("stock_batches.id"), nullable=False)
    goods_receipt_id = db.Column(db.Integer, db.ForeignKey("goods_receipts.id"), nullable=False)
    qty = db.Column(db.Numeric(12, 3), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)  # what the supplier owes back: PO rate − discount + GST
    reason = db.Column(db.String(200), nullable=False)
    # The debit note (a supplier payment of type debit_note) that carries the money
    debit_note_id = db.Column(db.Integer, db.ForeignKey("supplier_payments.id"), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    supplier = db.relationship("Supplier")
    product = db.relationship("Product")
    goods_receipt = db.relationship("GoodsReceipt")
    debit_note = db.relationship("SupplierPayment")
    created_by = db.relationship("User")

    def __repr__(self) -> str:
        return f"<SupplierReturn {self.return_number} qty={self.qty} amount={self.amount}>"
