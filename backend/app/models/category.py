"""Category model (self-referencing parent_id)."""
from app.extensions import db
from app.models.base import TimestampMixin


class Category(TimestampMixin, db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Profit wanted on cost, in % (12 = sell at cost × 1.12 before GST). NULL = parent's, else Settings default.
    target_margin_percent = db.Column(db.Numeric(6, 2), nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "target_margin_percent IS NULL OR (target_margin_percent >= 0 AND target_margin_percent <= 1000)",
            name="ck_categories_target_margin_range",
        ),
    )

    parent = db.relationship("Category", remote_side="Category.id", back_populates="children")
    children = db.relationship("Category", back_populates="parent")
    products = db.relationship("Product", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"
