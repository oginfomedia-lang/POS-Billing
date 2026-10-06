// Enter CASH/CARD/UPI amounts, show change.
import { type FormEvent, useState } from 'react';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import type { TenderMethod } from '../../types/sale';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';

const METHODS: { value: TenderMethod; label: string }[] = [
  { value: 'cash', label: 'Cash' },
  { value: 'card', label: 'Card' },
  { value: 'upi', label: 'UPI' },
];

interface Props {
  total: string;
  busy: boolean;
  error: string;
  onConfirm: (method: TenderMethod, cashTendered?: string, reference?: string) => void;
  onClose: () => void;
}

export function PaymentDialog({ total, busy, error, onConfirm, onClose }: Props) {
  const [method, setMethod] = useState<TenderMethod>('cash');
  const [tendered, setTendered] = useState(total);
  const [reference, setReference] = useState('');
  useKeyboardShortcuts({ Escape: onClose });

  const totalPaise = toPaise(total);
  const tenderedPaise = toPaise(tendered);
  const cashValid = Number.isFinite(tenderedPaise) && tenderedPaise >= totalPaise;
  const canConfirm = !busy && (method !== 'cash' || cashValid);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canConfirm) return;
    if (method === 'cash') onConfirm('cash', paiseToString(tenderedPaise));
    else onConfirm(method, undefined, reference.trim() || undefined);
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h3>Payment — {formatRupees(total)}</h3>

        <div className="pay-tabs" role="tablist">
          {METHODS.map((m) => (
            <button
              key={m.value}
              type="button"
              role="tab"
              aria-selected={method === m.value}
              className={`pay-tab${method === m.value ? ' active' : ''}`}
              onClick={() => setMethod(m.value)}
            >
              {m.label}
            </button>
          ))}
        </div>

        {error && <div className="form-error">{error}</div>}

        <form onSubmit={handleSubmit} className="modal-form">
          {method === 'cash' ? (
            <>
              <label className="field-label">
                Cash tendered
                <input
                  className="field-input pay-amount"
                  inputMode="decimal"
                  value={tendered}
                  onChange={(e) => setTendered(e.target.value)}
                  onFocus={(e) => e.target.select()}
                  autoFocus
                />
              </label>
              <div className={`change-due${cashValid ? '' : ' short'}`}>
                {cashValid
                  ? <>Change: <strong>{formatRupees(paiseToString(tenderedPaise - totalPaise))}</strong></>
                  : 'Tendered amount is less than the total.'}
              </div>
            </>
          ) : (
            <label className="field-label">
              {method === 'card' ? 'Card slip / approval no.' : 'UPI transaction ID'} (optional)
              <input
                key={method}
                className="field-input"
                value={reference}
                maxLength={100}
                onChange={(e) => setReference(e.target.value)}
                autoFocus
              />
            </label>
          )}

          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={!canConfirm}>
              {busy ? 'Processing…' : 'Confirm Payment'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
