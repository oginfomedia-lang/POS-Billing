// Card / UPI taken on the shop's own card machine or UPI QR sticker (Settings → Card & UPI payments → Manual).
// The app can't see that money: the cashier checks it arrived, then completes the bill with the dialog's button.
import { useTranslation } from 'react-i18next';
import type { DigitalMethod } from '../../types/sale';
import { formatRupees } from '../../utils/money';

interface Props {
  method: DigitalMethod;
  total: string;
  reference: string;
  onReferenceChange: (value: string) => void;
}

export function ManualPaymentPanel({ method, total, reference, onReferenceChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="digital-payment-section">
      <div className="digital-pay-box">
        <strong className="digital-pay-amount">{formatRupees(total)}</strong>
        <span className="digital-wait">
          {t(method === 'card' ? 'pay.cardInfo' : 'pay.upiInfo', { amount: formatRupees(total) })}
        </span>
      </div>
      <label className="field-label">
        <span>{t(method === 'card' ? 'pay.cardRef' : 'pay.upiRef')}</span>
        <input
          className="field-input"
          value={reference}
          maxLength={100}
          autoComplete="off"
          onChange={(e) => onReferenceChange(e.target.value)}
        />
      </label>
    </div>
  );
}
