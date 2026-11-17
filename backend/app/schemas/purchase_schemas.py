"""Schemas for Purchase Management module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import PurchaseStatus
from app.schemas.product_schemas import _optional_hsn


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
    # For the goods receipt screen (filled in by _enrich_po).
    product_details_pending: bool = False
    product_mrp: Decimal | None = None
    product_hsn_code: str | None = None



class PurchaseOrderOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    po_number: str
    supplier_id: int
    supplier_name: str = ""
    supplier_phone: str | None = None
    supplier_email: str | None = None
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
    # Sent to the supplier (sent_via: email / whatsapp / phone / in_person / other) and the latest email attempt.
    sent_at: datetime | None = None
    sent_via: str | None = None
    sent_by_name: str = ""
    email_status: str | None = None  # sending / sent / failed
    email_to: str | None = None
    email_error: str | None = None
    is_direct:bool = False  # goods arrived without a PO; entered from the supplier's bill
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


# Email isn't here: an email is recorded by the app itself when it goes out.
ManualSentVia = Literal["whatsapp", "phone", "in_person", "other"]


class MarkSentRequest(BaseModel):
    """Staff record how they sent the PO themselves."""

    via: ManualSentVia


class SupplierMessageOut(BaseModel):
    """What the "Send to supplier" box needs: the order as text, and which ways of sending are possible."""

    text: str
    whatsapp_url: str | None  # wa.me link with the text; None when the supplier has no valid mobile
    supplier_mobile: str | None
    supplier_email: str | None
    email_configured: bool  # Settings → Integrations → Email is filled in


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
    # With the godown switched on, goods go into the godown; True = put straight on the shop shelf (milk, bread).
    to_shop: bool = False
    # From the supplier's bill, all optional. A rate / GST different from the PO corrects the PO line itself
    # (only before any goods of that line came in), so stock cost, supplier balance and Tally use the bill.
    bill_unit_price: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)  # before discount & GST
    bill_tax_rate: Decimal | None = Field(None, ge=0, le=100, max_digits=5, decimal_places=2)
    mrp: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)  # printed on the goods, incl. GST
    hsn_code: str | None = Field(None, max_length=8)

    _hsn = field_validator("hsn_code", mode="before")(classmethod(lambda cls, v: _optional_hsn(v)))



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

class DirectPurchaseLine(BaseModel):
    """One line of the supplier's bill."""
    product_id: int
    qty: Decimal = Field(..., gt=0, max_digits=12, decimal_places=3)
    unit_price: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)  # rate on the bill, before GST
    tax_rate: Decimal = Field(Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2)
    mrp: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    hsn_code: str | None = Field(None, max_length=8)
    batch_number: str | None = Field(None, max_length=100)
    expiry_date: date | None = None
    to_shop: bool = False  # False = into the godown (the default when the godown is on); True = straight on the shelf

    _hsn = field_validator("hsn_code", mode="before")(classmethod(lambda cls, v: _optional_hsn(v)))


class DirectPurchaseCreate(BaseModel):
    """Goods arrived without a PO: the supplier's bill, entered once. The bill's file comes separately."""
    supplier_id: int
    store_id: int  # the store the goods went to
    invoice_number: str = Field(..., min_length=1, max_length=100)
    invoice_date: date
    due_date: date | None = None  # empty = from the supplier's payment terms
    other_charges: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    grand_total: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)  # as printed on the bill
    difference_reason: str | None = Field(None, max_length=1000)  # when the bill total differs from the lines
    notes: str | None = None
    items: list[DirectPurchaseLine] = Field(..., min_length=1)

    @model_validator(mode="after")
    def one_line_per_product(self):
        ids = [i.product_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("A product is listed twice. Put its total quantity on one line.")
        return self
