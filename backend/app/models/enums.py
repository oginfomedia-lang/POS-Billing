"""Enums: UserRole, SaleStatus, PaymentMethod, InventoryTxnType, ShiftStatus, DiscountType, NotificationStatus."""
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    CASHIER = "cashier"


class SaleStatus(str, enum.Enum):
    OPEN = "open"
    PAID = "paid"
    VOIDED = "voided"
    HELD = "held"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    SPLIT = "split"


class InventoryTxnType(str, enum.Enum):
    PURCHASE = "purchase"
    SALE = "sale"
    RETURN = "return"
    ADJUSTMENT = "adjustment"


class ShiftStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"
    BUY_X_GET_Y = "buy_x_get_y"  # buy `buy_qty` units, get `get_qty` more of the same product free
    QTY_PRICE = "qty_price"  # `buy_qty` units for `value` rupees incl. GST (e.g. 3 for ₹99)


class DiscountScope(str, enum.Enum):
    BILL = "bill"
    PRODUCT = "product"
    CATEGORY = "category"


class BarcodeType(str, enum.Enum):
    MANUFACTURER = "MANUFACTURER"
    IN_HOUSE = "IN_HOUSE"
    PRICE_EMBEDDED = "PRICE_EMBEDDED"


class UOMType(str, enum.Enum):
    PCS = "pcs"
    KG = "kg"
    G = "g"
    LTR = "ltr"
    ML = "ml"
    PACK = "pack"

class PaymentIntentStatus(str, enum.Enum):
    PENDING = "pending"      # QR shown / amount pushed to card machine, waiting for customer
    PAID = "paid"            # Razorpay confirmed the money; sale completed
    FAILED = "failed"        # card declined / machine error
    CANCELLED = "cancelled"  # cashier cancelled, or QR expired




class NotificationStatus(str, enum.Enum):
    PENDING = "pending"  # row claimed, message not confirmed yet (or the run crashed mid-send)
    SENT = "sent"
    FAILED = "failed"
