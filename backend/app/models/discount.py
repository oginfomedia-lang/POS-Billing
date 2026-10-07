"""Discount model (PERCENT/FLAT/BUY_X_GET_Y/QTY_PRICE, BILL/PRODUCT/CATEGORY scope).

Discounts apply automatically while billing. FIXED means rupees off each unit for
PRODUCT/CATEGORY scope, and rupees off the whole bill for BILL scope.
BUY_X_GET_Y and QTY_PRICE apply to PRODUCT/CATEGORY scope only.
"""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import DiscountScope, DiscountType


class Discount(TimestampMixin, db.Model):
    __tablename__ = "discounts"
    __table_args__ = (db.CheckConstraint("value >= 0", name="value_not_negative"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    discount_type = db.Column(db.Enum(DiscountType, name="discount_type"), nullable=False)
    value = db.Column(db.Numeric(12, 2), nullable=False)
    scope = db.Column(db.Enum(DiscountScope, name="discount_scope"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)  # PRODUCT scope
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)  # CATEGORY scope
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True)  # NULL = all stores
    min_bill_amount = db.Column(db.Numeric(12, 2), nullable=True)  # BILL scope only
    max_discount_amount = db.Column(db.Numeric(12, 2), nullable=True)  # cap for PERCENTAGE offers
    buy_qty = db.Column(db.Integer, nullable=True)  # BUY_X_GET_Y: units paid; QTY_PRICE: bundle size
    get_qty = db.Column(db.Integer, nullable=True)  # BUY_X_GET_Y: units free
    starts_at = db.Column(db.DateTime(timezone=True), nullable=True)
    ends_at = db.Column(db.DateTime(timezone=True), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    product = db.relationship("Product")
    category = db.relationship("Category")

    @property
    def product_name(self) -> str | None:
        return self.product.name if self.product else None

    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category else None

    def __repr__(self) -> str:
        return f"<Discount {self.name}>"
