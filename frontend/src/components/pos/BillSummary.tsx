// Subtotal, discount, GST, round-off, grand total.
import type { SaleOut } from '../../types/sale';
import { formatRupees } from '../../utils/money';
import { IconCreditCard, IconSparkles } from '../common/Icons';

interface Props {
  sale: SaleOut | null;
  onPayClick?: () => void;
  disabled?: boolean;
}

export function BillSummary({ sale, onPayClick, disabled }: Props) {
  const itemCount = sale?.items.reduce((n, i) => n + i.qty, 0) ?? 0;
  const hasDiscount = sale !== null && Number(sale.discount_amount) > 0;
  const hasItems = itemCount > 0;

  return (
    <aside className="bill-summary">
      <div className="summary-header">
        <span className="summary-title">Bill Summary</span>
        <span className="item-count-badge">
          {itemCount} {itemCount === 1 ? 'Item' : 'Items'}
        </span>
      </div>

      <div className="summary-rows">
        <div className="summary-row">
          <span className="row-label">Subtotal</span>
          <span className="row-val">{formatRupees(sale?.subtotal ?? 0)}</span>
        </div>
        {hasDiscount && (
          <div className="summary-row summary-discount-row">
            <span className="row-label">
              <IconSparkles size={14} /> Total Savings
            </span>
            <span className="row-val discount-val">− {formatRupees(sale.discount_amount)}</span>
          </div>
        )}
        <div className="summary-row">
          <span className="row-label">GST / Tax</span>
          <span className="row-val">{formatRupees(sale?.tax_amount ?? 0)}</span>
        </div>
      </div>

      <div className="summary-total-container">
        <div className="summary-row summary-total">
          <span className="total-label">Grand Total</span>
          <span className="total-amount">{formatRupees(sale?.total ?? 0)}</span>
        </div>

        {onPayClick && (
          <button
            className="btn-pay-now"
            disabled={!hasItems || disabled}
            onClick={onPayClick}
          >
            <IconCreditCard size={20} />
            <span>PAY NOW (F12)</span>
          </button>
        )}
      </div>
    </aside>
  );
}

