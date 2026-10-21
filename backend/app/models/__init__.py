"""Imports every model so Alembic can detect all tables."""
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.customer import Customer, RewardTransaction  # noqa: F401
from app.models.discount import Discount  # noqa: F401
from app.models.inventory import Inventory, InventoryTransaction, SaleItemBatch, StockBatch  # noqa: F401
from app.models.notification import NotificationLog  # noqa: F401
from app.models.product import Product, ProductBarcode  # noqa: F401
from app.models.returns import SaleReturn, SaleReturnItem  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.payment_intent import PaymentIntent  # noqa: F401
from app.models.sale import BillSequence, Sale, SaleItem  # noqa: F401
from app.models.shift import CashierShift  # noqa: F401
from app.models.store import Counter, Store  # noqa: F401
from app.models.system import SystemSetting  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.backup import BackupRun  # noqa: F401
from app.models.supplier import Supplier  # noqa: F401
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, GoodsReceipt, GoodsReceiptItem  # noqa: F401
from app.models.cloud_upload import CloudUploadAttempt  # noqa: F401
from app.models.restore_record import RestoreRecord  # noqa: F401
from app.models.replication_snapshot import ReplicationSnapshot  # noqa: F401
from app.models.supplier_product import SupplierProduct  # noqa: F401
from app.models.supplier_invoice import SupplierInvoice, SupplierInvoiceGRN  # noqa: F401
from app.models.supplier_payment import SupplierPayment, SupplierPaymentAllocation  # noqa: F401
from app.models.supplier_document import SupplierDocument  # noqa: F401
