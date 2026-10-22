// Main checkout screen: scan, cart, totals, payment.
import axios from 'axios';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { BarcodeInput } from '../../components/pos/BarcodeInput';
import { BillSummary } from '../../components/pos/BillSummary';
import { CartTable } from '../../components/pos/CartTable';
import { HoldBillDialog } from '../../components/pos/HoldBillDialog';
import { WeightDialog } from '../../components/pos/WeightDialog';
import { ManualDiscountDialog } from '../../components/pos/ManualDiscountDialog';
import { PaymentDialog } from '../../components/pos/PaymentDialog';
import { ShortcutBar } from '../../components/pos/ShortcutBar';
import {
  IconArrowLeft,
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
import { openDrawer } from '../../services/hardware/printerService';
import type { ManualDiscountInput } from '../../services/api/billingApi';
import { useBillStore } from '../../store/billStore';
import type { ProductOut } from '../../types/product';
import type { SaleItemOut, SaleOut, TenderMethod } from '../../types/sale';
import { useShiftStore } from '../../store/shiftStore';
import { useServerStatusStore } from '../../hooks/useServerStatus';
import { hasOfflineSupport } from '../../offline/sync';
import { useStores } from '../../store/storeContext';

import { formatRupees } from '../../utils/money';

type Dialog = 'pay' | 'hold' | null;

export function BillingPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  // The store this till is billing for: the open shift's store (same one printed on the bill).
  const shiftStoreId = useShiftStore((s) => s.shift?.store_id) ?? user?.store_id;
  const storeName = useStores().find((s) => s.id === shiftStoreId)?.name ?? t('pos.counterFallback');
  const {
    sale, busy, createDraft, addItem, updateItem, removeItem, setManualDiscount, hold, complete, markPaid, setCustomerMobile, redeemPoints,
    void: voidBill,
  } = useBillStore();

  const [error, setError] = useState('');
  const [draftFailed, setDraftFailed] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [dialogError, setDialogError] = useState('');
  // Cart line whose manual-discount dialog is open (null = closed).
  const [discountItem, setDiscountItem] = useState<SaleItemOut | null>(null);
  // Loose item picked by name: asking for its weight (null = closed).
  const [weightProduct, setWeightProduct] = useState<ProductOut | null>(null);
  const noPopup = dialog === null && discountItem === null && weightProduct === null;

  const hasItems = (sale?.items.length ?? 0) > 0;
  const serverDown = useServerStatusStore((s) => s.status === 'offline');

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
      // A weighing-scale sticker comes back with the weight (kg) to bill.
      const scanRes = await getProductByBarcode(code, sale?.store_id ?? shiftStoreId ?? undefined);
      const qty = scanRes.is_variable_weight && scanRes.weight_kg ? scanRes.weight_kg : 1;
      await addItem(scanRes.product.id, qty);
    });
  }

  /** Product picked from the name/SKU suggestions: add one; a loose item asks for its weight first. */
  function handlePick(product: ProductOut) {
    if (product.is_variable_weight) {
      setWeightProduct(product);
      return;
    }
    act(() => addItem(product.id, 1));
  }

  function handleWeight(kg: number) {
    const product = weightProduct;
    setWeightProduct(null);
    if (product) act(() => addItem(product.id, kg));
  }

  function openDialog(d: Exclude<Dialog, null>) {
    if (!hasItems || busy) return;
    setDialogError('');
    setDialog(d);
  }

  function handleVoid() {
    if (!hasItems || busy) return;
    if (window.confirm(t('pos.voidConfirm'))) act(voidBill);
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
      if (method === 'cash') openDrawer(); // don't wait: a drawer problem must not hold up the bill
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
    F4: () => navigate('/pos/returns'),
    F12: () => openDialog('pay'),
    Escape: handleVoid,
  };
  useKeyboardShortcuts(shortcuts, noPopup);

  return (
    <div className="billing-page">
      <header className="billing-topbar">
        <div className="pos-brand-tag">
          <IconShoppingCart size={22} color="#4f46e5" />
          <span className="pos-counter-title" title={storeName}>{storeName}</span>
        </div>
        <BarcodeInput
          onScan={handleScan}
          onPick={handlePick}
          active={noPopup}
          storeId={shiftStoreId}
        />
        <div className="billing-meta">
          {/* The cashier's name opens their bills on this shift (to check the cash before closing). */}
          <button
            type="button"
            className="cashier-chip cashier-chip-link"
            onClick={() => navigate('/pos/shift/bills')}
            title={t('shift.myBillsHint')}
            aria-label={t('shift.myBills')}
          >
            <span className="cashier-name">{user?.full_name || user?.username}</span>
            <span className="bill-id-badge">{sale ? `#${sale.id}` : t('pos.starting')}</span>
          </button>
          {(user?.role === 'admin' || user?.role === 'manager') && (
            <button className="btn-secondary btn-icon" onClick={() => navigate('/admin')}>
              <IconDashboard size={15} />
              <span>{t('pos.admin')}</span>
            </button>
          )}
          <button className="btn-secondary btn-icon" onClick={() => navigate('/pos/shift/close')}>
            <IconFileText size={15} />
            <span>{t('pos.shift')}</span>
          </button>
          <button className="btn-logout-icon" onClick={logout} title={t('common.logout')}>
            <IconLogOut size={16} />
          </button>
        </div>
      </header>

      {serverDown && hasOfflineSupport() && (
        <div className="page-error">
          <span>{t('offline.serverDown')}</span>
          <button className="btn-sm error-retry" onClick={() => navigate('/pos/offline')}>{t('offline.goOffline')}</button>
        </div>
      )}

      {error && (
        <div className="page-error">
          <span>{error}</span>
          {draftFailed && (
            <button className="btn-sm error-retry" onClick={() => { setError(''); setDraftFailed(false); }}>
              {t('common.retry')}
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
          { key: 'F2', label: t('pos.holdBill'), icon: IconPauseCircle, variant: 'warning', onClick: shortcuts.F2, disabled: !hasItems },
          { key: 'F3', label: t('pos.heldBills'), icon: IconFileText, variant: 'default', onClick: shortcuts.F3 },
          { key: 'F4', label: t('pos.returns'), icon: IconArrowLeft, variant: 'default', onClick: shortcuts.F4 },
          { key: 'F12', label: t('pos.payNow'), icon: IconCreditCard, variant: 'primary', onClick: shortcuts.F12, disabled: !hasItems },
          { key: 'Esc', label: t('pos.voidBill'), icon: IconTrash, variant: 'danger', onClick: shortcuts.Escape, disabled: !hasItems },
        ]}
      />

      {/* Mobile Sticky Payment Bar */}
      <div className="mobile-checkout-bar">
        <div className="mobile-total-info">
          <span className="mobile-total-label">{t('pos.totalAmount')}</span>
          <span className="mobile-total-val">{formatRupees(sale?.total ?? 0)}</span>
        </div>
        <button
          className="mobile-pay-btn"
          disabled={!hasItems || busy}
          onClick={() => openDialog('pay')}
        >
          <IconCreditCard size={18} />
          <span>{t('pos.payNowF12')}</span>
        </button>
      </div>

      {dialog === 'pay' && sale && (
        <PaymentDialog
          saleId={sale.id}
          total={sale.total}
          customerMobile={sale.customer_mobile}
          onSaveMobile={setCustomerMobile}
          pointsRedeemed={sale.points_redeemed}
          roomForReward={Number(sale.subtotal) - Number(sale.discount_amount) + Number(sale.reward_discount)}
          onRedeem={redeemPoints}
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
      {weightProduct && (
        <WeightDialog
          product={weightProduct}
          busy={busy}
          onConfirm={handleWeight}
          onClose={() => setWeightProduct(null)}
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

