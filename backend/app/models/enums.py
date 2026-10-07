"""Enums: UserRole, SaleStatus, PaymentMethod, InventoryTxnType, ShiftStatus, DiscountType."""
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


