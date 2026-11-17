// Modal dialog for updating a customer's credit limit.
import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { updateCustomerCreditLimit } from '../../services/api/customerApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { CustomerOut } from '../../types/customer';
import { formatRupees } from '../../utils/money';
import { IconCheck, IconX } from '../common/Icons';

interface Props {
  customer: CustomerOut;
  onClose: () => void;
  onSuccess: (updated: CustomerOut) => void;
}

export function CustomerCreditLimitDialog({ customer, onClose, onSuccess }: Props) {
  const { t } = useTranslation();
  const [limit, setLimit] = useState(customer.credit_limit ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useKeyboardShortcuts({ Escape: onClose });

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');

    try {
      const val = limit.trim() ? limit.trim() : null;
      const updated = await updateCustomerCreditLimit(customer.id, val);
      onSuccess(updated);
    } catch (err) {
      setError(getErrorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 440 }}>
        <div className="modal-header">
          <h3>{t('customers.setCreditLimitTitle', 'Set Credit Limit (क्रेडिट मर्यादा)')}</h3>
          <button type="button" className="btn-icon" onClick={onClose} aria-label={t('common.close')}>
            <IconX size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-form">
          {error && <div className="page-error">{error}</div>}

          <p className="hint-text">
            {t(
              'customers.creditLimitHint',
              'Set the maximum amount of Udhari this customer can take. Leave blank for unlimited.',
            )}
          </p>

          <div className="table-card" style={{ padding: 12, background: 'var(--surface-2, #f8fafc)', marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontWeight: 600 }}>{customer.name || customer.mobile}</span>
              <span>{customer.mobile}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.95em' }}>
              <span>{t('customers.currentLimit', 'Current Limit')}:</span>
              <strong>{customer.credit_limit ? formatRupees(customer.credit_limit) : t('customers.unlimited', 'Unlimited')}</strong>
            </div>
          </div>

          <label className="field-label">
            <span>{t('customers.newCreditLimit', 'New Credit Limit (₹)')}</span>
            <input
              type="number"
              step="100"
              min="0"
              placeholder="e.g. 5000 (blank = unlimited)"
              className="field-input"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              autoFocus
            />
          </label>

          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            {[1000, 2000, 5000, 10000].map((preset) => (
              <button
                key={preset}
                type="button"
                className="btn-sm"
                onClick={() => setLimit(String(preset))}
              >
                ₹{preset}
              </button>
            ))}
            <button
              type="button"
              className="btn-sm"
              onClick={() => setLimit('')}
            >
              {t('customers.unlimited', 'Unlimited')}
            </button>
          </div>

          <div className="modal-buttons" style={{ marginTop: 20 }}>
            <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>
              {t('common.cancel')}
            </button>
            <button type="submit" className="btn-primary" disabled={busy}>
              <IconCheck size={18} />
              <span>{busy ? t('common.saving') : t('common.save')}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
