// Subtotal, discount, GST, round-off, grand total.
import type { SaleOut } from '../../types/sale';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';
import { IconCreditCard, IconSparkles } from '../common/Icons';

interface Props {
  sale: SaleOut | null;
  onPayClick?: () => void;
  disabled?: boolean;
}

export function BillSummary({ sale, onPayClick, disabled }: Props) {
  const itemCount = sale?.items.reduce((n, i) => n + i.qty, 0) ?? 0;
  // Item offers + manual discounts = total discount minus the bill offer. Paise avoids float errors.
  const itemSavingsPaise = sale ? toPaise(sale.discount_amount) - toPaise(sale.bill_offer_discount) : 0;
  const hasBillOffer = sale !== null && sale.bill_offer_name !== null && Number(sale.bill_offer_discount) > 0;
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
        {itemSavingsPaise > 0 && (
          <div className="summary-row summary-discount-row">
            <span className="row-label"><IconSparkles size={14} /> Item offers</span>
            <span className="row-val discount-val">− {formatRupees(paiseToString(itemSavingsPaise))}</span>
          </div>
        )}
        {hasBillOffer && (
          <div className="summary-row summary-discount-row">
            <span className="row-label"><IconSparkles size={14} /> {sale.bill_offer_name}</span>
            <span className="row-val discount-val">− {formatRupees(sale.bill_offer_discount)}</span>
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

