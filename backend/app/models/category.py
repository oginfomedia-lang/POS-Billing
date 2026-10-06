"""Category model (self-referencing parent_id)."""
from app.extensions import db
from app.models.base import TimestampMixin


class Category(TimestampMixin, db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    parent = db.relationship("Category", remote_side="Category.id", back_populates="children")
    children = db.relationship("Category", back_populates="parent")
    products = db.relationship("Product", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"
