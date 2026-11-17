// Cash: enter amount, show change. Card/UPI: Razorpay pushes the exact total and the bill closes itself,
// or (manual mode) the cashier takes it on the shop's own machine / QR and confirms.
import type { ParseKeys } from 'i18next';
import React, { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { type CardUpiMode, getPaymentMode } from '../../services/api/billingApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { SaleOut, TenderMethod } from '../../types/sale';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';
import { normalizeMobile } from '../../utils/phone';
import { IconCash, IconCheck, IconCreditCard, IconQrCode, IconX, IconUsers } from '../common/Icons';
import { DigitalPaymentPanel } from './DigitalPaymentPanel';
import { ManualPaymentPanel } from './ManualPaymentPanel';
import { getCustomerCredit } from '../../services/api/customerApi';
import type { CustomerCreditInfo } from '../../types/customer';
import { RewardsStrip } from './RewardsStrip';

const METHODS: { value: TenderMethod; label: ParseKeys; icon: React.FC<{ size?: number }> }[] = [
  { value: 'cash', label: 'methods.cash', icon: IconCash },
  { value: 'card', label: 'methods.card', icon: IconCreditCard },
  { value: 'upi', label: 'pay.upiQr', icon: IconQrCode },
  { value: 'credit', label: 'methods.credit', icon: IconUsers },
];

const QUICK_CASH_PRESETS = [100, 200, 500, 2000];

interface Props {
  saleId: number;
  total: string;
  /** Saved on the bill already (full number), or null. */
  customerMobile: string | null;
  /** Saves the optional mobile on the open bill; throws with the server's message on failure. */
  onSaveMobile: (mobile: string | null) => Promise<void>;
  /** Reward points reserved on the bill. */
  pointsRedeemed: number;
  /** Bill amount before GST that a reward can still come off. */
  roomForReward: number;
  onRedeem: (blocks: number) => Promise<void>;
  busy: boolean;
  error: string;
  /** Cash, and card/UPI in manual mode. Razorpay card/UPI are reported through onDigitalPaid. */
  onConfirm: (method: TenderMethod, cashTendered?: string, reference?: string) => void;
  onDigitalPaid: (sale: SaleOut) => void;
  onClose: () => void;
}

export function PaymentDialog({
  saleId, total, customerMobile, onSaveMobile, pointsRedeemed, roomForReward, onRedeem, busy, error, onConfirm, onDigitalPaid, onClose,
}: Props) {
  const { t } = useTranslation();
  const [method, setMethod] = useState<TenderMethod>('cash');
  const [tendered, setTendered] = useState(total);
  const [mobile, setMobile] = useState(customerMobile ?? '');
  const [mobileError, setMobileError] = useState('');
  const [savingMobile, setSavingMobile] = useState(false);
  const [cardUpiMode, setCardUpiMode] = useState<CardUpiMode | null>(null);
  const [reference, setReference] = useState('');
  const [creditInfo, setCreditInfo] = useState<CustomerCreditInfo | null>(null);
  const [loadingCredit, setLoadingCredit] = useState(false);
  const normalizedMobile = normalizeMobile(mobile); // '' = none, null = invalid
  const mobileInvalid = normalizedMobile === null;
  useKeyboardShortcuts({ Escape: onClose });
  useEffect(() => {
    let cancelled = false;
    getPaymentMode()
      .then((mode) => { if (!cancelled) setCardUpiMode(mode); })
      .catch(() => { if (!cancelled) setCardUpiMode('razorpay'); }); // Razorpay panel shows its own error
    return () => { cancelled = true; };
  }, []);
  // Redeeming points changes the total: keep the cash box in step.
  useEffect(() => { setTendered(total); }, [total]);

   // Fetch live credit info whenever a valid 10-digit mobile is typed
  useEffect(() => {
    if (!normalizedMobile || normalizedMobile.length !== 10) {
      setCreditInfo(null);
      return;
    }
    let cancelled = false;
    setLoadingCredit(true);
    getCustomerCredit(normalizedMobile)
      .then((info) => { if (!cancelled) setCreditInfo(info); })
      .catch(() => { if (!cancelled) setCreditInfo(null); })
      .finally(() => { if (!cancelled) setLoadingCredit(false); });
    return () => { cancelled = true; };
  }, [normalizedMobile]);

  const totalPaise = toPaise(total);
  const tenderedPaise = toPaise(tendered);
  const cashValid = Number.isFinite(tenderedPaise) && tenderedPaise >= totalPaise;
  const manualDigital = (method === 'card' || method === 'upi') && cardUpiMode === 'manual';
  const creditTotal = Number(total) || 0;
  const currentCreditBalance = Number(creditInfo?.credit_balance || '0');
  const creditLimit = creditInfo?.credit_limit !== null && creditInfo?.credit_limit !== undefined ? Number(creditInfo.credit_limit) : null;
  const creditLimitExceeded = creditLimit !== null && (currentCreditBalance + creditTotal) > creditLimit;
  const creditValid = method === 'credit' && Boolean(normalizedMobile) && !mobileInvalid && !creditLimitExceeded;

  const canConfirm = !busy && !savingMobile && !mobileInvalid && (
    method === 'cash' ? cashValid :
    method === 'credit' ? creditValid :
    manualDigital
  );

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
    if (method === 'cash') onConfirm('cash', paiseToString(tenderedPaise));
    else if (method === 'credit') onConfirm('credit', undefined, reference.trim() || undefined);
    else onConfirm(method, undefined, reference.trim() || undefined);
  }

  function chooseMethod(next: TenderMethod) {
    // Card/UPI complete on the server as soon as the customer pays: save the number before that starts.
    saveMobile();
    setMethod(next);
    setReference('');
  }

  function handleQuickCash(amount: number) {
    setTendered(String(amount));
  }

  return (
    <div className="modal-overlay">
      <div className="modal-box payment-dialog-box">
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
        <RewardsStrip
          mobile={customerMobile}
          pointsRedeemed={pointsRedeemed}
          roomForReward={roomForReward}
          onRedeem={onRedeem}
          disabled={busy || savingMobile}
        />

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
                   ) : method === 'credit' ? (
            <div className="manual-pay-panel" style={{ padding: '16px 0' }}>
              {!normalizedMobile ? (
                <div className="page-error" style={{ background: 'var(--warn-bg)', color: 'var(--warn-text)', borderColor: 'var(--warn-text)', display: 'block' }}>
                  {t('pay.creditMobileRequired')}
                </div>
              ) : loadingCredit ? (
                <p className="digital-wait">{t('common.loading')}</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {creditLimitExceeded && (
                    <div className="page-error" style={{ display: 'block' }}>
                      {t('pay.creditLimitExceeded')}
                    </div>
                  )}

                  <div className="table-card" style={{ padding: 12, background: 'var(--surface-2, #f8fafc)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <span>{t('pay.creditCurrentDues')}:</span>
                      <strong>{formatRupees(creditInfo?.credit_balance ?? '0')}</strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, color: 'var(--primary, #2563eb)' }}>
                      <span>{t('pay.creditThisBill')}:</span>
                      <strong>+ {formatRupees(total)}</strong>
                    </div>
                    <hr style={{ margin: '8px 0', border: 'none', borderTop: '1px solid var(--border, #e2e8f0)' }} />
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '1.1em' }}>
                      <span style={{ fontWeight: 600 }}>{t('pay.creditAfterBill')}:</span>
                      <strong style={{ color: creditLimitExceeded ? 'var(--error, #dc2626)' : 'inherit' }}>
                        {formatRupees((currentCreditBalance + creditTotal).toFixed(2))}
                      </strong>
                    </div>
                    {creditLimit !== null && (
                      <div style={{ fontSize: '0.85em', color: 'var(--text-muted, #64748b)', marginTop: 6 }}>
                        {t('pay.creditLimit')}: {formatRupees(creditLimit.toFixed(2))}
                      </div>
                    )}
                  </div>

                  <label className="field-label" style={{ marginTop: 4 }}>
                    {t('common.note')} ({t('common.optional' as ParseKeys)})
                    <input
                      className="field-input"
                      placeholder="e.g. will pay on Friday"
                      value={reference}
                      onChange={(e) => setReference(e.target.value)}
                      maxLength={100}
                    />
                  </label>
                </div>
              )}
            </div>
          ) : cardUpiMode === null ? (
            <p className="digital-wait">{t('common.loading')}</p>
          ) : manualDigital ? (
            <ManualPaymentPanel method={method} total={total} reference={reference} onReferenceChange={setReference} />
          ) : (
            <DigitalPaymentPanel
              key={method}
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
                        {(method === 'cash' || method === 'credit' || manualDigital) && (
              <button type="submit" className="btn-primary btn-confirm-pay" disabled={!canConfirm}>
                <IconCheck size={18} />
                <span>
                  {busy
                    ? t('pay.processing')
                    : method === 'credit'
                    ? t('pay.confirmCredit')
                    : t(method === 'cash' ? 'pay.complete' : 'pay.manualReceived')}
                </span>
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
