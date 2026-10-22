"""Supplier CRUD, product mapping, financial summary and ledger."""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select

from app.errors.exceptions import BadRequestError, ConflictError, NotFoundError
from app.extensions import db
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice
from app.models.supplier_payment import SupplierPayment
from app.models.supplier_product import SupplierProduct
from app.models.user import User
from app.schemas.supplier_schemas import (
    SupplierCreate,
    SupplierDashboard,
    SupplierLedgerEntry,
    SupplierProductCreate,
    SupplierProductOut,
    SupplierProductUpdate,
    SupplierSummary,
    SupplierUpdate,
)
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


# ── Supplier-Product Mapping ──────────────────────────────────────────────────

def get_supplier_products(supplier_id: int) -> list[SupplierProductOut]:
    get_supplier(supplier_id)
    rows = list(
        db.session.scalars(
            select(SupplierProduct)
            .where(SupplierProduct.supplier_id == supplier_id)
            .order_by(SupplierProduct.id)
        ).all()
    )
    out = []
    for sp in rows:
        item = SupplierProductOut.model_validate(sp)
        if sp.product:
            item.product_name = sp.product.name
            item.product_sku = sp.product.sku
        out.append(item)
    return out


def add_supplier_product(supplier_id: int, data: SupplierProductCreate, actor: User | None) -> SupplierProductOut:
    get_supplier(supplier_id)
    product = db.session.get(Product, data.product_id)
    if product is None:
        raise NotFoundError(f"Product {data.product_id} not found.")
    existing = db.session.scalar(
        select(SupplierProduct).where(
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.product_id == data.product_id,
        )
    )
    if existing:
        raise ConflictError(f"Product '{product.name}' is already mapped to this supplier.")
    with transaction():
        sp = SupplierProduct(
            supplier_id=supplier_id,
            product_id=data.product_id,
            supplier_product_code=data.supplier_product_code,
            purchase_price=data.purchase_price,
            min_order_qty=data.min_order_qty,
            lead_time_days=data.lead_time_days,
            is_preferred=data.is_preferred,
            notes=data.notes,
            is_active=data.is_active,
        )
        db.session.add(sp)
        db.session.flush()
        audit_service.log(actor, "supplier_product.add", "supplier_product", sp.id,
                          new_values={"supplier_id": supplier_id, "product_id": data.product_id})
    item = SupplierProductOut.model_validate(sp)
    item.product_name = product.name
    item.product_sku = product.sku
    return item


def update_supplier_product(
    supplier_id: int, sp_id: int, data: SupplierProductUpdate, actor: User | None
) -> SupplierProductOut:
    sp = db.session.scalar(
        select(SupplierProduct).where(
            SupplierProduct.id == sp_id,
            SupplierProduct.supplier_id == supplier_id,
        )
    )
    if sp is None:
        raise NotFoundError(f"Supplier product mapping {sp_id} not found.")
    old_price = sp.purchase_price
    with transaction():
        for field, val in data.model_dump(exclude_unset=True).items():
            setattr(sp, field, val)
        if data.purchase_price is not None and data.purchase_price != old_price:
            sp.last_purchase_price = old_price
        audit_service.log(actor, "supplier_product.update", "supplier_product", sp.id, None, None)
    item = SupplierProductOut.model_validate(sp)
    if sp.product:
        item.product_name = sp.product.name
        item.product_sku = sp.product.sku
    return item


def remove_supplier_product(supplier_id: int, sp_id: int, actor: User | None) -> None:
    sp = db.session.scalar(
        select(SupplierProduct).where(
            SupplierProduct.id == sp_id,
            SupplierProduct.supplier_id == supplier_id,
        )
    )
    if sp is None:
        raise NotFoundError(f"Supplier product mapping {sp_id} not found.")
    with transaction():
        audit_service.log(actor, "supplier_product.remove", "supplier_product", sp.id, None, None)
        db.session.delete(sp)


def get_products_for_po(supplier_id: int) -> list[dict]:
    """Active mapped products for the PO form, with the rate to start each line at.

    purchase_price: the supplier's rate (the last goods receipt sets it), else the product's default cost,
    else None: the user must type it. The selling price is never used as a purchase rate; it is sent
    separately so the form can warn when the rate is not below it.
    """
    rows = db.session.execute(
        select(SupplierProduct, Product)
        .join(Product, SupplierProduct.product_id == Product.id)
        .where(SupplierProduct.supplier_id == supplier_id)
        .where(SupplierProduct.is_active.is_(True))
        .where(Product.is_active.is_(True))
        .order_by(Product.name)
    ).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "purchase_price": _po_rate(sp, p),
            "last_purchase_price": float(sp.last_purchase_price) if sp.last_purchase_price is not None else None,
            "selling_price": float(p.price),
            "tax_rate": float(p.tax_rate),
            "supplier_product_code": sp.supplier_product_code,
            "min_order_qty": float(sp.min_order_qty) if sp.min_order_qty else 1,
            "is_preferred": sp.is_preferred,
        }
        for sp, p in rows
    ]


# ── Financial summary ─────────────────────────────────────────────────────────

def get_supplier_summary(supplier_id: int) -> SupplierSummary:
    """Money with this supplier. What is owed comes from the invoices' payable amounts (= goods received),
    not from the PO amounts."""
    supplier = get_supplier(supplier_id)
    from datetime import date

    from app.models.enums import InvoiceVerificationStatus, PurchaseStatus, SupplierInvoiceStatus
    from app.models.purchase import PurchaseOrder
    from app.services import purchase_service

    total_po = db.session.scalar(
        select(func.coalesce(func.sum(PurchaseOrder.grand_total), 0))
        .where(PurchaseOrder.supplier_id == supplier_id)
        .where(PurchaseOrder.status != PurchaseStatus.CANCELLED)
    ) or Decimal("0")

    grns = purchase_service.supplier_grns(supplier_id)
    received = sum((g.value for g in grns), Decimal("0"))
    not_invoiced = sum((g.value for g in grns if g.invoice_id is None), Decimal("0"))

    invoices = db.session.scalars(
        select(SupplierInvoice)
        .where(SupplierInvoice.supplier_id == supplier_id)
        .where(SupplierInvoice.payment_status != SupplierInvoiceStatus.CANCELLED)
    ).all()
    invoiced = sum((Decimal(str(i.grand_total)) for i in invoices), Decimal("0"))
    payable = sum((Decimal(str(i.payable_amount)) for i in invoices), Decimal("0"))
    paid = sum((Decimal(str(i.amount_paid)) for i in invoices), Decimal("0"))
    today = date.today()
    overdue = sum(
        (max(Decimal(str(i.payable_amount)) - Decimal(str(i.amount_paid)), Decimal("0"))
         for i in invoices if i.due_date and i.due_date < today),
        Decimal("0"),
    )
    disputed = sum(1 for i in invoices if i.verification_status == InvoiceVerificationStatus.DISPUTED)

    payment_count = db.session.scalar(
        select(func.count(SupplierPayment.id))
        .where(SupplierPayment.supplier_id == supplier_id)
        .where(SupplierPayment.is_voided.is_(False))
    ) or 0

    opening = Decimal(str(supplier.opening_balance))
    from app.services import supplier_payment_service
    advance = supplier_payment_service.advance_balance(supplier_id)
    return SupplierSummary(
        supplier_id=supplier_id,
        total_po_value=float(total_po),
        total_received_value=float(received),
        not_invoiced_value=float(not_invoiced),
        total_invoiced=float(invoiced),
        total_payable=float(payable),
        total_paid=float(paid),
        outstanding_balance=float(opening + payable - paid - advance),  # net of unused advance, like the ledger
        advance_balance=float(advance),
        overdue_amount=float(overdue),
        invoice_count=len(invoices),
        disputed_count=disputed,
        payment_count=payment_count,
    )


def get_supplier_ledger(supplier_id: int, date_from: str | None = None, date_to: str | None = None) -> list[SupplierLedgerEntry]:
    """Build a running ledger from invoices and payments."""
    from app.models.enums import SupplierInvoiceStatus, SupplierPaymentType
    entries: list[dict] = []

    inv_q = select(SupplierInvoice).where(
        SupplierInvoice.supplier_id == supplier_id,
        SupplierInvoice.payment_status != SupplierInvoiceStatus.CANCELLED,
    )
    if date_from:
        inv_q = inv_q.where(SupplierInvoice.invoice_date >= date_from)
    if date_to:
        inv_q = inv_q.where(SupplierInvoice.invoice_date <= date_to)
    for inv in db.session.scalars(inv_q).all():
        # The shop owes the payable amount (goods received), which can be less than the bill.
        description = f"Invoice {inv.invoice_number}"
        if inv.payable_amount != inv.grand_total:
            description += f" (billed ₹{inv.grand_total}, payable ₹{inv.payable_amount} for goods received)"
        entries.append({
            "date": str(inv.invoice_date),
            "entry_type": "invoice",
            "reference": inv.invoice_number,
            "description": description,
            "debit": float(inv.payable_amount),
            "credit": 0.0,
        })

    pay_q = select(SupplierPayment).where(
        SupplierPayment.supplier_id == supplier_id,
        SupplierPayment.is_voided.is_(False),
    )
    if date_from:
        pay_q = pay_q.where(SupplierPayment.payment_date >= date_from)
    if date_to:
        pay_q = pay_q.where(SupplierPayment.payment_date <= date_to)
    for pay in db.session.scalars(pay_q).all():
        entries.append({
            "date": str(pay.payment_date),
            "entry_type": pay.payment_type.value,
            "reference": pay.reference_number or f"PAY-{pay.id}",
            "description": f"Payment {pay.payment_type.value}",
            "debit": 0.0,
            "credit": float(pay.amount),
        })

    entries.sort(key=lambda x: x["date"])

    supplier = get_supplier(supplier_id)
    balance = float(supplier.opening_balance)
    result: list[SupplierLedgerEntry] = []
    for e in entries:
        balance += e["debit"] - e["credit"]
        result.append(SupplierLedgerEntry(
            date=e["date"],
            entry_type=e["entry_type"],
            reference=e["reference"],
            description=e["description"],
            debit=e["debit"],
            credit=e["credit"],
            balance=round(balance, 2),
        ))
    return result


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


def _po_rate(sp: SupplierProduct, p: Product) -> float | None:
    if sp.purchase_price is not None:
        return float(sp.purchase_price)
    if p.cost_price is not None:
        return round(float(p.cost_price), 2)
    return None
