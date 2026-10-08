// Main checkout screen: scan, cart, totals, payment.
import axios from 'axios';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarcodeInput } from '../../components/pos/BarcodeInput';
import { BillSummary } from '../../components/pos/BillSummary';
import { CartTable } from '../../components/pos/CartTable';
import { HoldBillDialog } from '../../components/pos/HoldBillDialog';
import { ManualDiscountDialog } from '../../components/pos/ManualDiscountDialog';
import { PaymentDialog } from '../../components/pos/PaymentDialog';
import { ShortcutBar } from '../../components/pos/ShortcutBar';
import {
  IconCreditCard,
  IconDashboard,
  IconFileText,
  IconLogOut,
  IconPauseCircle,
  IconShoppingCart,
  IconTrash,
} from '../../components/common/Icons';
import { useAuth } from '../../hooks/useAuth';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getErrorMessage } from '../../services/api/httpClient';
import { getProductByBarcode } from '../../services/api/productApi';
import type { ManualDiscountInput } from '../../services/api/billingApi';
import { useBillStore } from '../../store/billStore';
import type { SaleItemOut, SaleOut, TenderMethod } from '../../types/sale';
import { formatRupees } from '../../utils/money';

type Dialog = 'pay' | 'hold' | null;

export function BillingPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const {
    sale, busy, createDraft, addItem, updateItem, removeItem, setManualDiscount, hold, complete, markPaid, void: voidBill,
  } = useBillStore();

  const [error, setError] = useState('');
  const [draftFailed, setDraftFailed] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [dialogError, setDialogError] = useState('');
  // Cart line whose manual-discount dialog is open (null = closed).
  const [discountItem, setDiscountItem] = useState<SaleItemOut | null>(null);

  const hasItems = (sale?.items.length ?? 0) > 0;

  // Whenever there is no bill (first load, or after pay/hold/void), start one.
  useEffect(() => {
    if (sale || busy || draftFailed) return;
    createDraft().catch((err) => {
      setDraftFailed(true);
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        navigate('/pos/shift/open', { replace: true });
      } else {
        setError(getErrorMessage(err));
      }
    });
  }, [sale, busy, draftFailed, createDraft, navigate]);

  /** Runs a cart action and shows its error in the page banner. */
  async function act(fn: () => Promise<void>) {
    setError('');
    try {
      await fn();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  function handleScan(code: string) {
    act(async () => {
      const scanRes = await getProductByBarcode(code);
      const qty = scanRes.is_variable_weight && scanRes.weight_kg ? scanRes.weight_kg : 1;
      await addItem(scanRes.product.id, qty);
    });
  }

  function openDialog(d: Exclude<Dialog, null>) {
    if (!hasItems || busy) return;
    setDialogError('');
    setDialog(d);
  }

  function handleVoid() {
    if (!hasItems || busy) return;
    if (window.confirm('Void this bill? All items will be removed.')) act(voidBill);
  }

  async function handleHold(note: string) {
    setDialogError('');
    try {
      await hold(note || undefined);
      setDialog(null);
    } catch (err) {
      setDialogError(getErrorMessage(err));
    }
  }

  async function handlePay(method: TenderMethod, cashTendered?: string, reference?: string) {
    setDialogError('');
    try {
      const paid = await complete(method, cashTendered, reference);
      setDialog(null);
      navigate(`/pos/reprint/${paid.id}?print=1`);
    } catch (err) {
      setDialogError(getErrorMessage(err));
    }
  }

  /** Card/UPI: Razorpay confirmed and the backend already completed the bill. Same receipt flow as cash. */
  function handleDigitalPaid(paid: SaleOut) {
    markPaid();
    setDialog(null);
    navigate(`/pos/reprint/${paid.id}?print=1`);
  }

  async function handleManualDiscount(data: ManualDiscountInput) {
    if (!discountItem) return;
    setDialogError('');
    try {
      await setManualDiscount(discountItem.id, data);
      setDiscountItem(null);
    } catch (err) {
      setDialogError(getErrorMessage(err));
    }
  }

  const shortcuts = {
    F2: () => openDialog('hold'),
    F3: () => navigate('/pos/held'),
    F12: () => openDialog('pay'),
    Escape: handleVoid,
  };
  useKeyboardShortcuts(shortcuts, dialog === null && discountItem === null);

  return (
    <div className="billing-page">
      <header className="billing-topbar">
        <div className="pos-brand-tag">
          <IconShoppingCart size={22} color="#4f46e5" />
          <span className="pos-counter-title">POS Counter</span>
        </div>
        <BarcodeInput onScan={handleScan} active={dialog === null && discountItem === null} />
        <div className="billing-meta">
          <div className="cashier-chip">
            <span className="cashier-name">{user?.full_name || user?.username}</span>
            <span className="bill-id-badge">{sale ? `#${sale.id}` : 'Starting…'}</span>
          </div>
          {(user?.role === 'admin' || user?.role === 'manager') && (
            <button className="btn-secondary btn-icon" onClick={() => navigate('/admin')}>
              <IconDashboard size={15} />
              <span>Admin</span>
            </button>
          )}
          <button className="btn-secondary btn-icon" onClick={() => navigate('/pos/shift/close')}>
            <IconFileText size={15} />
            <span>Shift</span>
          </button>
          <button className="btn-logout-icon" onClick={logout} title="Logout">
            <IconLogOut size={16} />
          </button>
        </div>
      </header>

      {error && (
        <div className="page-error">
          <span>{error}</span>
          {draftFailed && (
            <button className="btn-sm error-retry" onClick={() => { setError(''); setDraftFailed(false); }}>
              Retry
            </button>
          )}
        </div>
      )}

      <div className="billing-body">
        <section className="billing-cart">
          <CartTable
            items={sale?.items ?? []}
            disabled={busy}
            onQtyChange={(itemId, qty) => act(() => updateItem(itemId, qty))}
            onRemove={(itemId) => act(() => removeItem(itemId))}
            onManualDiscount={(item) => { setDialogError(''); setDiscountItem(item); }}
          />
        </section>
        <BillSummary
          sale={sale}
          disabled={busy}
          onPayClick={() => openDialog('pay')}
        />
      </div>

      <ShortcutBar
        shortcuts={[
          { key: 'F2', label: 'Hold Bill', icon: IconPauseCircle, variant: 'warning', onClick: shortcuts.F2, disabled: !hasItems },
          { key: 'F3', label: 'Held Bills', icon: IconFileText, variant: 'default', onClick: shortcuts.F3 },
          { key: 'F12', label: 'Pay Now', icon: IconCreditCard, variant: 'primary', onClick: shortcuts.F12, disabled: !hasItems },
          { key: 'Esc', label: 'Void Bill', icon: IconTrash, variant: 'danger', onClick: shortcuts.Escape, disabled: !hasItems },
        ]}
      />

      {/* Mobile Sticky Payment Bar */}
      <div className="mobile-checkout-bar">
        <div className="mobile-total-info">
          <span className="mobile-total-label">Total Amount</span>
          <span className="mobile-total-val">{formatRupees(sale?.total ?? 0)}</span>
        </div>
        <button
          className="mobile-pay-btn"
          disabled={!hasItems || busy}
          onClick={() => openDialog('pay')}
        >
          <IconCreditCard size={18} />
          <span>PAY NOW (F12)</span>
        </button>
      </div>

      {dialog === 'pay' && sale && (
        <PaymentDialog
          saleId={sale.id}
          total={sale.total}
          busy={busy}
          error={dialogError}
          onConfirm={handlePay}
          onDigitalPaid={handleDigitalPaid}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'hold' && (
        <HoldBillDialog
          busy={busy}
          error={dialogError}
          onConfirm={handleHold}
          onClose={() => setDialog(null)}
        />
      )}
      {discountItem && (
        <ManualDiscountDialog
          item={discountItem}
          busy={busy}
          error={dialogError}
          onConfirm={handleManualDiscount}
          onClose={() => setDiscountItem(null)}
        />
      )}
    </div>
  );
}

