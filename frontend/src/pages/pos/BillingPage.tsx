// Main checkout screen: scan, cart, totals, payment.
import axios from 'axios';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarcodeInput } from '../../components/pos/BarcodeInput';
import { BillSummary } from '../../components/pos/BillSummary';
import { CartTable } from '../../components/pos/CartTable';
import { HoldBillDialog } from '../../components/pos/HoldBillDialog';
import { PaymentDialog } from '../../components/pos/PaymentDialog';
import { ShortcutBar } from '../../components/pos/ShortcutBar';
import { useAuth } from '../../hooks/useAuth';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getErrorMessage } from '../../services/api/httpClient';
import { getProductByBarcode } from '../../services/api/productApi';
import { useBillStore } from '../../store/billStore';
import type { TenderMethod } from '../../types/sale';

type Dialog = 'pay' | 'hold' | null;

export function BillingPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { sale, busy, createDraft, addItem, updateItem, removeItem, hold, complete, void: voidBill } =
    useBillStore();

  const [error, setError] = useState('');
  const [draftFailed, setDraftFailed] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [dialogError, setDialogError] = useState('');

  const hasItems = (sale?.items.length ?? 0) > 0;

  // Whenever there is no bill (first load, or after pay/hold/void), start one.
  useEffect(() => {
    if (sale || busy || draftFailed) return;
    createDraft().catch((err) => {
      setDraftFailed(true);
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        navigate('/pos/open-shift', { replace: true });
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
      const product = await getProductByBarcode(code);
      await addItem(product.id);
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
      navigate(`/pos/reprint/${paid.id}`);
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
  useKeyboardShortcuts(shortcuts, dialog === null);

  return (
    <div className="billing-page">
      <header className="billing-topbar">
        <BarcodeInput onScan={handleScan} active={dialog === null} />
        <div className="billing-meta">
          <span>{user?.full_name}</span>
          <span className="status-muted">{sale ? `Bill #${sale.id}` : 'Starting bill…'}</span>
          <button className="btn-secondary" onClick={() => navigate('/pos')}>Menu</button>
        </div>
      </header>

      {error && (
        <div className="page-error">
          {error}
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
          />
        </section>
        <BillSummary sale={sale} />
      </div>

      <ShortcutBar
        shortcuts={[
          { key: 'F2', label: 'Hold', onClick: shortcuts.F2, disabled: !hasItems },
          { key: 'F3', label: 'Held Bills', onClick: shortcuts.F3 },
          { key: 'F12', label: 'Pay', onClick: shortcuts.F12, disabled: !hasItems },
          { key: 'Esc', label: 'Void', onClick: shortcuts.Escape, disabled: !hasItems },
        ]}
      />

      {dialog === 'pay' && sale && (
        <PaymentDialog
          total={sale.total}
          busy={busy}
          error={dialogError}
          onConfirm={handlePay}
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
    </div>
  );
}
