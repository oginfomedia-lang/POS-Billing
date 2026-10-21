"""Offline billing: the catalogue counters keep for when the server is unreachable, and recording the cash bills
they made meanwhile once they can upload them.

While offline the counter prices bills itself with the same rules (frontend src/offline/pricing.ts mirrors
pricing_service and discount_service.choose_best_offer). On upload the bill is recorded exactly as the customer
paid it: the server recomputes every line's tax and the totals from the amounts sent, and refuses the bill if they
don't add up, but it doesn't choose offers again (they may have changed since).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.errors.exceptions import AppError, NotFoundError, PermissionDeniedError
from app.extensions import db
from app.models.category import Category
from app.models.discount import Discount
from app.models.enums import SaleStatus
from app.models.product import Product
from app.models.sale import Sale, SaleItem
from app.models.shift import CashierShift
from app.models.user import User
from app.repositories.store_repository import StoreRepository
from app.schemas.offline_schemas import (
    OfflineCatalogOut,
    OfflineOffer,
    OfflineProduct,
    OfflineSaleIn,
    OfflineSettings,
    OfflineStore,
)
from app.services import audit_service, inventory_service, payment_service, pricing_service, settings_service
from app.utils.transactions import transaction

# A counter's clock can be a little ahead of the server's; a bill dated further ahead than this is refused.
MAX_CLOCK_AHEAD = timedelta(minutes=10)


def catalog(store_id: int) -> OfflineCatalogOut:
    store = StoreRepository().get_by_id(store_id)
    if store is None:
        raise NotFoundError(f"Store {store_id} not found.")
    products = db.session.scalars(
        db.select(Product)
        .where(Product.is_active.is_(True), (Product.store_id.is_(None)) | (Product.store_id == store_id))
        .order_by(Product.id)
    ).all()
    prices = inventory_service.store_prices(store_id, [p.id for p in products])
    # Offers that are on now or start later (the counter may be offline when they start). Ended ones are left out.
    now = datetime.now(timezone.utc)
    offers = db.session.scalars(
        db.select(Discount).where(
            Discount.is_active.is_(True),
            (Discount.store_id.is_(None)) | (Discount.store_id == store_id),
            (Discount.ends_at.is_(None)) | (Discount.ends_at > now),
        ).order_by(Discount.id)
    ).all()
    s = settings_service.get_settings()
    return OfflineCatalogOut(
        generated_at=now,
        store=OfflineStore(id=store.id, name=store.name, address=store.address, phone=store.phone, gstin=store.gstin),
        settings=OfflineSettings(
            scale_prefix=s.scale_prefix, scale_plu_digits=s.scale_plu_digits, scale_value=s.scale_value,
            receipt_header=s.receipt_header, receipt_footer=s.receipt_footer,
            receipt_footer_mr=s.receipt_footer_mr, fssai_number=s.fssai_number,
        ),
        products=[
            OfflineProduct(
                id=p.id, name=p.name, sku=p.sku, barcode=p.barcodes[0].barcode if p.barcodes else None,
                plu_code=p.plu_code, category_id=p.category_id, price=prices.get(p.id, p.price),
                tax_rate=p.tax_rate, mrp=p.mrp, hsn_code=p.hsn_code, uom=p.uom, is_variable_weight=p.is_variable_weight,
            )
            for p in products
        ],
        offers=[OfflineOffer.model_validate(d, from_attributes=True) for d in offers],
        categories=dict(db.session.execute(db.select(Category.id, Category.parent_id)).all()),
    )


def record_sale(data: OfflineSaleIn, actor: User) -> tuple[Sale, bool]:
    """Returns (sale, created). Uploading the same bill again returns the one already recorded."""
    existing = db.session.scalar(db.select(Sale).where(Sale.offline_id == data.offline_id))
    if existing is not None:
        if existing.cashier_id != actor.id:
            raise PermissionDeniedError("This bill belongs to another cashier.")
        return existing, False

    shift = db.session.get(CashierShift, data.shift_id)
    if shift is None or shift.user_id != actor.id:
        raise PermissionDeniedError("This bill's shift is not yours.")
    billed_at = data.billed_at if data.billed_at.tzinfo else data.billed_at.replace(tzinfo=timezone.utc)
    if billed_at > datetime.now(timezone.utc) + MAX_CLOCK_AHEAD:
        raise AppError("The bill's date is in the future. Check this counter's clock.")
    if db.session.scalar(db.select(Sale.id).where(Sale.bill_number == data.bill_number)):
        raise AppError(f"Bill number {data.bill_number} is already used by another bill.")

    with transaction():
        sale = Sale(
            store_id=shift.store_id, counter_id=shift.counter_id, shift_id=shift.id, cashier_id=actor.id,
            status=SaleStatus.PAID, offline_id=data.offline_id, bill_number=data.bill_number,
            bill_offer_id=data.bill_offer_id, bill_offer_name=data.bill_offer_name,
            bill_offer_discount=data.bill_offer_discount, completed_at=billed_at,
        )
        lines = []
        for ln in data.items:
            product = db.session.get(Product, ln.product_id)
            if product is None:
                raise NotFoundError(f"Product {ln.product_id} not found.")
            line_total, tax = pricing_service.line_amounts(ln.unit_price, ln.qty, ln.tax_rate, ln.discount_amount)
            if ln.discount_amount > line_total or ln.offer_discount > ln.discount_amount:
                raise AppError(f"{ln.product_name}: the discount is more than the line.")
            sale.items.append(SaleItem(
                product=product, product_name=ln.product_name, unit_price=ln.unit_price, tax_rate=ln.tax_rate,
                mrp=ln.mrp, hsn_code=ln.hsn_code, qty=ln.qty, line_total=line_total,
                discount_amount=ln.discount_amount, offer_id=ln.offer_id, offer_name=ln.offer_name,
                offer_discount=ln.offer_discount, tax_amount=tax,
                unit_cost=inventory_service.cost_price(shift.store_id, product),
            ))
            lines.append((line_total, ln.discount_amount, tax))
        totals = pricing_service.bill_totals(lines)
        if totals["total"] != data.total:
            raise AppError(
                f"The bill's total ({data.total}) doesn't match its lines ({totals['total']}).",
                details={"expected_total": str(totals["total"])},
            )
        sale.subtotal, sale.discount_amount = totals["subtotal"], totals["discount_amount"]
        sale.tax_amount, sale.total = totals["tax_amount"], totals["total"]
        sale.payments.append(payment_service.build_payment("cash", sale.total, data.cash_tendered))
        db.session.add(sale)
        db.session.flush()
        shortages = inventory_service.deduct_for_offline_sale(sale.store_id, sale.items, sale.id)
        audit_service.log(
            actor, "sale.offline", "sale", sale.id, None,
            {"bill_number": sale.bill_number, "total": str(sale.total), "billed_at": billed_at.isoformat(),
             **({"stock_short": shortages} if shortages else {})},
        )
    return sale, True
