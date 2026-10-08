"""Store and Counter models."""
from app.extensions import db
from app.models.base import TimestampMixin


class Store(TimestampMixin, db.Model):
    __tablename__ = "stores"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    gstin = db.Column(db.String(20), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    users = db.relationship("User", back_populates="store")
    counters = db.relationship("Counter", back_populates="store", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Store {self.name}>"


class Counter(TimestampMixin, db.Model):
    __tablename__ = "counters"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    label = db.Column(db.String(100), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Razorpay POS card machine on this counter, e.g. "1490123456|ezetap_android". Empty = no card machine.
    edc_device_id = db.Column(db.String(100), nullable=True)

    store = db.relationship("Store", back_populates="counters")

    def __repr__(self) -> str:
        return f"<Counter {self.code}>"
