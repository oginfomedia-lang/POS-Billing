"""Supplier model."""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import PaymentTerms


class Supplier(TimestampMixin, db.Model):
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    supplier_code = db.Column(db.String(50), unique=True, nullable=False)
    company_name = db.Column(db.String(200), nullable=False)
    contact_person = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    alt_phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(200), nullable=True)
    gstin = db.Column(db.String(15), nullable=True)
    pan = db.Column(db.String(10), nullable=True)
    billing_address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(10), nullable=True)
    country = db.Column(db.String(100), nullable=False, default="India")
    payment_terms = db.Column(
        db.Enum(PaymentTerms, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PaymentTerms.NET_30,
    )
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    products = db.relationship("Product", back_populates="supplier", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Supplier {self.supplier_code} {self.company_name}>"
