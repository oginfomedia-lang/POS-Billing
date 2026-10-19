// Manager-approved discount on one bill line (e.g. damaged pack).
import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import type { ManualDiscountInput } from '../../services/api/billingApi';
import type { SaleItemOut } from '../../types/sale';
import { formatRupees, toPaise } from '../../utils/money';
import { IconPercent, IconX } from '../common/Icons';

interface Props {
  item: SaleItemOut;
  busy: boolean;
  error: string;
  onConfirm: (data: ManualDiscountInput) => void;
  onClose: () => void;
}

export function ManualDiscountDialog({ item, busy, error, onConfirm, onClose }: Props) {
  const { t } = useTranslation();
  const hasDiscount = Number(item.manual_discount) > 0;
  const [amount, setAmount] = useState(hasDiscount ? item.manual_discount : '');
  const [reason, setReason] = useState(item.manual_discount_reason ?? '');
  const [username, setUsername] = useState('');
  const [pin, setPin] = useState('');
  useKeyboardShortcuts({ Escape: onClose });

  const amountPaise = toPaise(amount);
  const tooMuch = amountPaise > toPaise(item.line_total);
  const hasApproval = username.trim() !== '' && pin.length >= 4;
  const canSubmit = !busy && amountPaise > 0 && !tooMuch && reason.trim() !== '' && hasApproval;

  function approval() {
    return { approver_username: username.trim(), approver_pin: pin };
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (canSubmit) onConfirm({ amount, reason: reason.trim(), ...approval() });
  }

  function handleRemove() {
    if (hasApproval) onConfirm({ amount: '0', reason: '', ...approval() });
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="modal-subtitle">{t('manualDiscount.subtitle')}</span>
            <div className="title-with-icon">
              <IconPercent size={20} color="#4f46e5" />
              <h3 className="modal-title">{t('manualDiscount.title')}</h3>
            </div>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose}>
            <IconX size={18} />
          </button>
        </div>

        <p className="hint-text">
          {t('manualDiscount.lineInfo', { product: item.product_name, amount: formatRupees(item.line_total) })}
        </p>
        {error && <div className="form-error">{error}</div>}

        <form onSubmit={handleSubmit} className="modal-form">
          <div className="form-row">
            <label className="field-label">
              {t('manualDiscount.amount')}
              <input className="field-input" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus />
            </label>
            <label className="field-label">
              {t('manualDiscount.reason')}
              <input className="field-input" maxLength={100} placeholder={t('manualDiscount.reasonPlaceholder')} value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          </div>
          {tooMuch && <div className="form-error">{t('manualDiscount.tooMuch')}</div>}

          <div className="form-row">
            <label className="field-label">
              {t('manualDiscount.managerUsername')}
              <input className="field-input" autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="field-label">
              {t('manualDiscount.managerPin')}
              <input className="field-input" type="password" autoComplete="off" maxLength={12} value={pin} onChange={(e) => setPin(e.target.value)} />
            </label>
          </div>

          <div className="modal-buttons">
            {hasDiscount && (
              <button type="button" className="btn-secondary" disabled={busy || !hasApproval} onClick={handleRemove}>
                {t('manualDiscount.remove')}
              </button>
            )}
            <button type="button" className="btn-secondary" onClick={onClose}>{t('common.cancel')}</button>
            <button type="submit" className="btn-primary" disabled={!canSubmit}>
              {busy ? t('manualDiscount.applying') : t('manualDiscount.approve')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
