// Modal dialog for recording customer Udhari dues repayments (Khata settlement).
import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { repayCustomerCredit } from '../../services/api/customerApi';
import { useStoreContext } from '../../store/storeContext';
import { getErrorMessage } from '../../services/api/httpClient';
import type { CreditTxnOut, CustomerOut } from '../../types/customer';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';
import { IconCheck, IconX } from '../common/Icons';

const REPAY_METHODS = [
  { value: 'cash', label: 'Cash (रोख)' },
  { value: 'upi', label: 'UPI / QR' },
  { value: 'card', label: 'Card' },
  { value: 'bank', label: 'Bank Transfer' },
] as const;

const QUICK_PRESETS = [100, 200, 500, 1000, 2000];

interface Props {
  customer: CustomerOut;
  onClose: () => void;
  onSuccess: (txn: CreditTxnOut) => void;
}

export function CustomerPaymentDialog({ customer, onClose, onSuccess }: Props) {
  const { t } = useTranslation();
  const currentDues = Number(customer.credit_balance) || 0;
  const [amount, setAmount] = useState(customer.credit_balance);
  const [method, setMethod] = useState<'cash' | 'upi' | 'card' | 'bank'>('cash');
  const [reference, setReference] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useKeyboardShortcuts({ Escape: onClose });

  // Head office has no store of its own: the money is recorded at the store picked in the sidebar.
  const storeId = useStoreContext((s) => s.selectedId);
  const amountPaise = toPaise(amount);
  const duesPaise = toPaise(customer.credit_balance);
  const overDues = Number.isFinite(amountPaise) && amountPaise > duesPaise;
  const isValidAmount = Number.isFinite(amountPaise) && amountPaise > 0 && !overDues;
  const newBalance = Math.max(0, currentDues - (amountPaise / 100));

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!isValidAmount || busy) return;
    setBusy(true);
    setError('');

    try {
      const txn = await repayCustomerCredit(customer.id, {
        amount: paiseToString(amountPaise),
        payment_method: method,
        reference: reference.trim() || undefined,
        note: note.trim() || undefined,
        store_id: storeId ?? undefined,
      });
      onSuccess(txn);
    } catch (err) {
      setError(getErrorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <div className="modal-header">
          <h3>{t('customers.receivePaymentTitle' as any, 'Receive Udhari Payment (जमा नोंदवा)')}</h3>
          <button type="button" className="btn-icon" onClick={onClose} aria-label={t('common.close')}>
            <IconX size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-form">
          {error && <div className="page-error">{error}</div>}

          {/* Customer info tile */}
          <div className="table-card" style={{ padding: 12, background: 'var(--surface-2, #f8fafc)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontWeight: 600 }}>{customer.name || customer.mobile}</span>
              <span style={{ color: 'var(--text-muted, #64748b)' }}>{customer.mobile}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '1.05em', marginTop: 8 }}>
              <span>{t('customers.colCredit' as any, 'Current Dues (बाकी रक्कम)')}:</span>
              <strong style={{ color: currentDues > 0 ? 'var(--error, #dc2626)' : 'inherit' }}>
                {formatRupees(customer.credit_balance)}
              </strong>
            </div>
          </div>

          {/* Amount input */}
          <label className="field-label">
            <span>{t('pay.amount' as any, 'Repayment Amount (जमा रक्कम)')}</span>
            <input
              type="number"
              step="0.01"
              min="0.01"
              max={customer.credit_balance}
              className="field-input pay-amount"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
              autoFocus
            />
            {overDues && (
              <span className="field-error">
                {t('customers.repayOverDues', { amount: formatRupees(customer.credit_balance) })}
              </span>
            )}
          </label>

          {/* Quick presets */}
          <div className="quick-cash-presets" style={{ marginTop: -4 }}>
            <button
              type="button"
              className="preset-chip"
              onClick={() => setAmount(customer.credit_balance)}
              style={{ fontWeight: 600 }}
            >
              {t('pay.payFull' as any, 'Full Dues: ')} {formatRupees(customer.credit_balance)}
            </button>
            {QUICK_PRESETS.map((amt) => (
              <button
                key={amt}
                type="button"
                className="preset-chip"
                onClick={() => setAmount(String(amt))}
              >
                ₹{amt}
              </button>
            ))}
          </div>

          {/* Payment Method */}
          <label className="field-label">
            <span>{t('pay.paymentMethod' as any, 'Payment Method (माध्यम)')}</span>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8, marginTop: 4 }}>
              {REPAY_METHODS.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  className={`btn-sm ${method === m.value ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ padding: '8px 12px', textAlign: 'center' }}
                  onClick={() => setMethod(m.value)}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </label>

          {/* Reference / UTR */}
          {method !== 'cash' && (
            <label className="field-label">
              <span>{t('pay.reference' as any, 'Reference / UTR / Cheque No.')} (optional)</span>
              <input
                className="field-input"
                placeholder="e.g. UPI Ref / Cheque No."
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                maxLength={100}
              />
            </label>
          )}

          {/* Note */}
          <label className="field-label">
            <span>{t('common.note')} (optional)</span>
            <input
              className="field-input"
              placeholder="e.g. Paid in cash at counter"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={255}
            />
          </label>

          {/* Balance Preview */}
          {isValidAmount && (
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: 'var(--surface-2, #f8fafc)', borderRadius: 6, fontSize: '0.9em' }}>
              <span>{t('customers.balanceAfterRepayment' as any, 'Balance after this payment')}:</span>
              <strong>{formatRupees(newBalance.toFixed(2))}</strong>
            </div>
          )}

          <div className="modal-buttons" style={{ marginTop: 16 }}>
            <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>
              {t('common.cancel')}
            </button>
            <button type="submit" className="btn-primary" disabled={!isValidAmount || busy}>
              <IconCheck size={18} />
              <span>{busy ? t('common.saving') : t('customers.confirmPayment' as any, 'Confirm Repayment (जमा करा)')}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
