// Cash: enter amount, show change. Card/UPI: Razorpay pushes the exact total and the bill closes itself.
import type { ParseKeys } from 'i18next';
import React, { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getErrorMessage } from '../../services/api/httpClient';
import type { SaleOut, TenderMethod } from '../../types/sale';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';
import { normalizeMobile } from '../../utils/phone';
import { IconCash, IconCheck, IconCreditCard, IconQrCode, IconX } from '../common/Icons';
import { DigitalPaymentPanel } from './DigitalPaymentPanel';

const METHODS: { value: TenderMethod; label: ParseKeys; icon: React.FC<{ size?: number }> }[] = [
  { value: 'cash', label: 'methods.cash', icon: IconCash },
  { value: 'card', label: 'methods.card', icon: IconCreditCard },
  { value: 'upi', label: 'pay.upiQr', icon: IconQrCode },
];

const QUICK_CASH_PRESETS = [100, 200, 500, 2000];

interface Props {
  saleId: number;
  total: string;
  /** Saved on the bill already (full number), or null. */
  customerMobile: string | null;
  /** Saves the optional mobile on the open bill; throws with the server's message on failure. */
  onSaveMobile: (mobile: string | null) => Promise<void>;
  busy: boolean;
  error: string;
  /** Cash only: card/UPI are confirmed by Razorpay and reported through onDigitalPaid. */
  onConfirm: (method: TenderMethod, cashTendered?: string, reference?: string) => void;
  onDigitalPaid: (sale: SaleOut) => void;
  onClose: () => void;
}

export function PaymentDialog({
  saleId, total, customerMobile, onSaveMobile, busy, error, onConfirm, onDigitalPaid, onClose,
}: Props) {
  const { t } = useTranslation();
  const [method, setMethod] = useState<TenderMethod>('cash');
  const [tendered, setTendered] = useState(total);
  const [mobile, setMobile] = useState(customerMobile ?? '');
  const [mobileError, setMobileError] = useState('');
  const [savingMobile, setSavingMobile] = useState(false);
  useKeyboardShortcuts({ Escape: onClose });

  const totalPaise = toPaise(total);
  const tenderedPaise = toPaise(tendered);
  const cashValid = Number.isFinite(tenderedPaise) && tenderedPaise >= totalPaise;
  const normalizedMobile = normalizeMobile(mobile); // '' = none, null = invalid
  const mobileInvalid = normalizedMobile === null;
  const canConfirm = !busy && !savingMobile && method === 'cash' && cashValid && !mobileInvalid;

  /** Saves the mobile on the bill if it changed. Returns false when it couldn't be saved. */
  async function saveMobile(): Promise<boolean> {
    if (normalizedMobile === null) return false;
    if (normalizedMobile === (customerMobile ?? '')) return true;
    setSavingMobile(true);
    setMobileError('');
    try {
      await onSaveMobile(normalizedMobile || null);
      return true;
    } catch (err) {
      setMobileError(getErrorMessage(err));
      return false;
    } finally {
      setSavingMobile(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!(await saveMobile())) return;
    if (!canConfirm) return;
    onConfirm('cash', paiseToString(tenderedPaise));
  }

  function chooseMethod(next: TenderMethod) {
    // Card/UPI complete on the server as soon as the customer pays: save the number before that starts.
    saveMobile();
    setMethod(next);
  }

  function handleQuickCash(amount: number) {
    setTendered(String(amount));
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box payment-dialog-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="modal-subtitle">{t('pay.subtitle')}</span>
            <h3 className="modal-title">{t('pay.title', { amount: formatRupees(total) })}</h3>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose}>
            <IconX size={18} />
          </button>
        </div>

        <div className="pay-tabs" role="tablist">
          {METHODS.map((m) => {
            const Icon = m.icon;
            return (
              <button
                key={m.value}
                type="button"
                role="tab"
                aria-selected={method === m.value}
                className={`pay-tab${method === m.value ? ' active' : ''}`}
                onClick={() => chooseMethod(m.value)}
              >
                <Icon size={18} />
                <span>{t(m.label)}</span>
              </button>
            );
          })}
        </div>

        {error && <div className="form-error">{error}</div>}

        <label className="field-label mobile-field">
          <span>{t('pay.customerMobile')}</span>
          <input
            className={`field-input${mobileInvalid ? ' input-invalid' : ''}`}
            type="tel"
            inputMode="numeric"
            autoComplete="off"
            maxLength={16}
            placeholder={t('pay.mobilePlaceholder')}
            value={mobile}
            onChange={(e) => { setMobile(e.target.value); setMobileError(''); }}
            onBlur={() => { saveMobile(); }}
          />
          {mobileInvalid && <span className="mobile-bad">{t('pay.mobileInvalid')}</span>}
          {!mobileInvalid && normalizedMobile !== '' && normalizedMobile === (customerMobile ?? '') && (
            <span className="mobile-ok">✓ {t('pay.mobileSaved')}</span>
          )}
          {mobileError && <span className="mobile-bad">{mobileError}</span>}
        </label>

        <form onSubmit={handleSubmit} className="modal-form">
          {method === 'cash' ? (
            <div className="cash-payment-section">
              <label className="field-label">
                <span>{t('pay.cashTendered')}</span>
                <input
                  className="field-input pay-amount"
                  inputMode="decimal"
                  value={tendered}
                  onChange={(e) => setTendered(e.target.value)}
                  onFocus={(e) => e.target.select()}
                  autoFocus
                />
              </label>

              <div className="quick-cash-presets">
                <span className="presets-label">{t('pay.quickCash')}</span>
                <button type="button" className="preset-chip" onClick={() => setTendered(total)}>
                  {t('pay.exact', { amount: formatRupees(total) })}
                </button>
                {QUICK_CASH_PRESETS.map((amt) => (
                  <button key={amt} type="button" className="preset-chip" onClick={() => handleQuickCash(amt)}>
                    ₹{amt}
                  </button>
                ))}
              </div>

              <div className={`change-due-box ${cashValid ? 'valid' : 'invalid'}`}>
                {cashValid ? (
                  <>
                    <span className="change-label">{t('pay.changeLabel')}</span>
                    <strong className="change-amount">
                      {formatRupees(paiseToString(tenderedPaise - totalPaise))}
                    </strong>
                  </>
                ) : (
                  <span className="change-warning">{t('pay.short', { amount: formatRupees(total) })}</span>
                )}
              </div>
            </div>
          ) : (
            <DigitalPaymentPanel
              key={method} // switching Card <-> UPI cancels the old request and starts a new one
              saleId={saleId}
              method={method}
              total={total}
              onPaid={onDigitalPaid}
            />
          )}

          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onClose}>
              {t('common.cancel')}
            </button>
            {method === 'cash' && (
              <button type="submit" className="btn-primary btn-confirm-pay" disabled={!canConfirm}>
                <IconCheck size={18} />
                <span>{busy ? t('pay.processing') : t('pay.complete')}</span>
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
