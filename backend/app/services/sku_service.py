"""Automatic SKUs: CATEGORY-PRODUCT-NUMBER, e.g. KIR-SAK-0001 (किराणा / साखर) or GRO-SUG-0002 (Grocery / Sugar).

The prefixes come from app/utils/sku_prefix.py. The number comes from the product_sku_seq database sequence:
shared by every store and counter, safe when several people save at the same moment, never reused (a deleted
product's number stays used; a failed save may leave a gap). products.sku is UNIQUE in the database as well.
"""
from __future__ import annotations

from sqlalchemy import text

from app.errors.exceptions import BadRequestError, ConflictError
from app.extensions import db
from app.models.category import Category
from app.models.product import PRODUCT_SKU_SEQ, Product
from app.utils.sku_prefix import CATEGORY_FALLBACK, PRODUCT_FALLBACK, sku_prefix

NUMBER_DIGITS = 4  # at least: 0001 ... 9999, then 10000 ...


def _category_name(category_id: int | None) -> str | None:
    """The category's name from the database (never from what the form sent)."""
    if category_id is None:
        return None
    category = db.session.get(Category, category_id)
    if category is None:
        raise BadRequestError(f"Category {category_id} not found.")
    return category.name


def prefix(category_id: int | None, product_name: str) -> str:
    """"KIR-SAK" for किराणा / साखर. No category (or no usable letters) uses CAT, an unusable name PRD."""
    return f"{sku_prefix(_category_name(category_id), CATEGORY_FALLBACK)}-{sku_prefix(product_name, PRODUCT_FALLBACK)}"


def _format(head: str, number: int) -> str:
    return f"{head}-{number:0{NUMBER_DIGITS}d}"


def generate(category_id: int | None, product_name: str) -> str:
    """A new SKU for a product being created. Takes a number from the sequence (so two saves at once never get
    the same one) and skips a code someone already typed by hand for another product."""
    head = prefix(category_id, product_name)
    for _ in range(1000):
        sku = _format(head, db.session.scalar(db.select(PRODUCT_SKU_SEQ.next_value())))
        if db.session.scalar(db.select(Product.id).where(Product.sku == sku)) is None:
            return sku
    raise ConflictError("Could not find a free SKU. Try again.")


def preview(category_id: int | None, product_name: str) -> dict:
    """What the next SKU would look like, for the Add Product form. Uses no number: the one shown is the
    sequence's next value now, and the saved product may get a later one if others save first."""
    head = prefix(category_id, product_name)
    last, called = db.session.execute(text("SELECT last_value, is_called FROM product_sku_seq")).one()
    return {"prefix": head, "sku": _format(head, last + 1 if called else last), "final": False}
