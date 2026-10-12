"""Supplier CRUD and dashboard statistics."""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select

from app.errors.exceptions import ConflictError, NotFoundError
from app.extensions import db
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.supplier_schemas import SupplierCreate, SupplierDashboard, SupplierUpdate
from app.services import audit_service
from app.utils.transactions import transaction


def _gen_code() -> str:
    return f"SUP-{uuid.uuid4().hex[:6].upper()}"


def _unique_code() -> str:
    for _ in range(10):
        code = _gen_code()
        if not db.session.scalar(select(Supplier).where(Supplier.supplier_code == code)):
            return code
    raise RuntimeError("Could not generate a unique supplier code after 10 attempts.")


def product_counts(supplier_ids: list[int]) -> dict[int, int]:
    if not supplier_ids:
        return {}
    rows = db.session.execute(
        select(Product.supplier_id, func.count(Product.id))
        .where(Product.supplier_id.in_(supplier_ids))
        .group_by(Product.supplier_id)
    ).all()
    return {sid: cnt for sid, cnt in rows}


def get_dashboard() -> SupplierDashboard:
    total = db.session.scalar(select(func.count(Supplier.id))) or 0
    active = db.session.scalar(
        select(func.count(Supplier.id)).where(Supplier.is_active.is_(True))
    ) or 0
    products_linked = db.session.scalar(
        select(func.count(Product.id)).where(Product.supplier_id.isnot(None))
    ) or 0
    return SupplierDashboard(
        total=total,
        active=active,
        inactive=total - active,
        products_linked=products_linked,
    )


def list_suppliers(
    page: int,
    per_page: int,
    is_active: bool | None,
    search: str | None,
) -> tuple[list[Supplier], int, dict[int, int]]:
    q = select(Supplier)
    if is_active is not None:
        q = q.where(Supplier.is_active.is_(is_active))
    if search:
        like = f"%{search}%"
        q = q.where(
            or_(
                Supplier.company_name.ilike(like),
                Supplier.supplier_code.ilike(like),
                Supplier.contact_person.ilike(like),
                Supplier.phone.ilike(like),
                Supplier.email.ilike(like),
                Supplier.gstin.ilike(like),
            )
        )
    total = db.session.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = list(
        db.session.scalars(
            q.order_by(Supplier.company_name).offset((page - 1) * per_page).limit(per_page)
        ).all()
    )
    counts = product_counts([s.id for s in items])
    return items, total, counts


def get_supplier(supplier_id: int) -> Supplier:
    s = db.session.get(Supplier, supplier_id)
    if not s:
        raise NotFoundError(f"Supplier #{supplier_id} not found.")
    return s


def create_supplier(data: SupplierCreate, actor: User | None) -> Supplier:
    code = (data.supplier_code or "").strip().upper() or _unique_code()
    if db.session.scalar(select(Supplier).where(Supplier.supplier_code == code)):
        raise ConflictError(f"Supplier code '{code}' is already in use.")
    if data.gstin:
        dup = db.session.scalar(select(Supplier).where(Supplier.gstin == data.gstin))
        if dup:
            raise ConflictError(
                f"GSTIN {data.gstin} is already used by {dup.company_name} ({dup.supplier_code})."
            )
    if data.phone:
        dup = db.session.scalar(select(Supplier).where(Supplier.phone == data.phone))
        if dup:
            raise ConflictError(
                f"Phone {data.phone} is already used by {dup.company_name} ({dup.supplier_code})."
            )
    supplier = Supplier(
        supplier_code=code,
        company_name=data.company_name,
        contact_person=data.contact_person,
        phone=data.phone,
        alt_phone=data.alt_phone,
        email=data.email,
        gstin=data.gstin,
        pan=data.pan,
        billing_address=data.billing_address,
        city=data.city,
        state=data.state,
        pincode=data.pincode,
        country=data.country or "India",
        payment_terms=data.payment_terms,
        notes=data.notes,
    )
    with transaction():
        db.session.add(supplier)
        db.session.flush()
        audit_service.log(
            actor, "supplier.create", "supplier", supplier.id,
            new_values={"code": supplier.supplier_code, "name": supplier.company_name},
        )
    return supplier


def update_supplier(supplier_id: int, data: SupplierUpdate, actor: User | None) -> Supplier:
    supplier = get_supplier(supplier_id)
    old = {"company_name": supplier.company_name, "is_active": supplier.is_active}
    new_gstin = data.gstin if "gstin" in data.model_fields_set else None
    new_phone = data.phone if "phone" in data.model_fields_set else None
    if new_gstin and new_gstin != supplier.gstin:
        dup = db.session.scalar(
            select(Supplier).where(Supplier.gstin == new_gstin, Supplier.id != supplier_id)
        )
        if dup:
            raise ConflictError(
                f"GSTIN {new_gstin} is already used by {dup.company_name} ({dup.supplier_code})."
            )
    if new_phone and new_phone != supplier.phone:
        dup = db.session.scalar(
            select(Supplier).where(Supplier.phone == new_phone, Supplier.id != supplier_id)
        )
        if dup:
            raise ConflictError(
                f"Phone {new_phone} is already used by {dup.company_name} ({dup.supplier_code})."
            )
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(supplier, field, val)
    with transaction():
        audit_service.log(
            actor, "supplier.update", "supplier", supplier.id,
            old_values=old,
            new_values={"company_name": supplier.company_name, "is_active": supplier.is_active},
        )
    return supplier
