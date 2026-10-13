"""Schemas for Purchase Management module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import PurchaseStatus


class PurchaseOrderItemCreate(BaseModel):
    product_id: int
    ordered_qty: Decimal = Field(..., gt=0, max_digits=12, decimal_places=3)
    unit_price: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    discount_percent: Decimal = Field(Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2)
    tax_rate: Decimal = Field(Decimal("0"), ge=0, max_digits=5, decimal_places=2)


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    store_id: int | None = None
    purchase_date: date
    expected_delivery_date: date | None = None
    reference_number: str | None = Field(None, max_length=100)
    notes: str | None = None
    internal_remarks: str | None = None
    shipping_charges: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    other_charges: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    shipping_address: str | None = None
    items: list[PurchaseOrderItemCreate] = Field(..., min_length=1)


class PurchaseOrderUpdate(BaseModel):
    supplier_id: int | None = None
    store_id: int | None = None
    purchase_date: date | None = None
    expected_delivery_date: date | None = None
    reference_number: str | None = Field(None, max_length=100)
    notes: str | None = None
    internal_remarks: str | None = None
    shipping_charges: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    other_charges: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    shipping_address: str | None = None
    items: list[PurchaseOrderItemCreate] | None = None


class PurchaseOrderItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    product_id: int
    product_name: str
    product_sku: str | None
    ordered_qty: Decimal
    received_qty: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    tax_rate: Decimal
    line_discount: Decimal
    tax_amount: Decimal
    line_total: Decimal


class PurchaseOrderOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    po_number: str
    supplier_id: int
    supplier_name: str = ""
    store_id: int | None
    purchase_date: date
    expected_delivery_date: date | None
    reference_number: str | None
    notes: str | None
    internal_remarks: str | None
    shipping_address: str | None = None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    shipping_charges: Decimal = Decimal("0")
    other_charges: Decimal = Decimal("0")
    grand_total: Decimal
    status: PurchaseStatus
    ordered_at: datetime | None
    approved_at: datetime | None = None
    approved_by_id: int | None = None
    cancelled_at: datetime | None
    closed_at: datetime | None = None
    created_by_id: int | None
    created_by_name: str = ""
    items: list[PurchaseOrderItemOut] = []
    created_at: datetime
    updated_at: datetime
    # Money, from the GRNs and the supplier invoices of this PO (payments are made on invoices).
    # payment_status: not_invoiced / unpaid / partially_paid / overdue / paid
    payment_status: str = "not_invoiced"
    received_value: Decimal = Decimal("0")  # goods accepted on the GRNs, at PO rates
    not_invoiced_value: Decimal = Decimal("0")  # received but no supplier invoice yet
    invoiced_amount: Decimal = Decimal("0")  # invoice totals as the supplier billed them
    payable_amount: Decimal = Decimal("0")  # what is owed: never more than the goods received
    amount_paid: Decimal = Decimal("0")
    outstanding_amount: Decimal = Decimal("0")  # payable − paid


class GoodsReceiptItemCreate(BaseModel):
    purchase_order_item_id: int
    qty_received: Decimal = Field(..., gt=0, max_digits=12, decimal_places=3)
    qty_accepted: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=3)
    qty_rejected: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    qty_damaged: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    batch_number: str | None = Field(None, max_length=100)
    mfg_date: date | None = None
    expiry_date: date | None = None
    remarks: str | None = None


class GoodsReceiptCreate(BaseModel):
    received_at: datetime | None = None
    notes: str | None = None
    items: list[GoodsReceiptItemCreate] = Field(..., min_length=1)


class GoodsReceiptItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    purchase_order_item_id: int
    product_id: int
    product_name: str = ""
    qty_received: Decimal
    qty_accepted: Decimal | None
    qty_rejected: Decimal
    qty_damaged: Decimal
    batch_number: str | None
    mfg_date: date | None
    expiry_date: date | None
    remarks: str | None


class GoodsReceiptOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    purchase_order_id: int
    receipt_number: str
    received_at: datetime
    received_by_id: int | None
    received_by_name: str = ""
    notes: str | None
    receipt_items: list[GoodsReceiptItemOut] = []
    created_at: datetime


class PurchaseDashboard(BaseModel):
    total: int
    total_value: Decimal
    pending: int
    ordered: int
    partially_received: int
    received: int
    cancelled: int
    total_paid: Decimal = Decimal("0")
    total_due: Decimal = Decimal("0")


class SupplierGRNOut(BaseModel):
    """A goods receipt on the supplier page: what it is worth and which invoice bills it."""

    id: int
    receipt_number: str
    purchase_order_id: int
    po_number: str
    received_at: datetime
    value: Decimal
    item_count: int
    invoice_id: int | None = None
    invoice_number: str | None = None


class POPaymentSummary(BaseModel):
    po_id: int
    grand_total: Decimal
    received_value: Decimal = Decimal("0")
    not_invoiced_value: Decimal = Decimal("0")
    invoiced_amount: Decimal = Decimal("0")
    payable_amount: Decimal = Decimal("0")
    total_paid: Decimal
    outstanding: Decimal
    invoice_count: int
    payment_status: str
    invoice_id: int | None
    invoice_ids: list[int] = []


class POPaymentEntry(BaseModel):
    payment_id: int
    payment_date: date
    amount: Decimal
    allocated_amount: Decimal
    payment_method: str
    reference_number: str | None
    notes: str | None
    is_voided: bool
    created_by_name: str
    running_total_paid: Decimal
    balance_after: Decimal
    invoice_number: str = ""


class POPaymentHistoryOut(BaseModel):
    po_id: int
    po_number: str
    supplier_name: str
    grand_total: Decimal
    payable_amount: Decimal = Decimal("0")
    total_paid: Decimal
    outstanding: Decimal
    payment_status: str
    invoice_number: str | None
    invoice_id: int | None
    entries: list[POPaymentEntry]
