// Subtotal, discount, GST, round-off, grand total.
import type { SaleOut } from '../../types/sale';
import { formatRupees } from '../../utils/money';

interface Props {
  sale: SaleOut | null;
}

export function BillSummary({ sale }: Props) {
  const itemCount = sale?.items.reduce((n, i) => n + i.qty, 0) ?? 0;
  const hasDiscount = sale !== null && Number(sale.discount_amount) > 0;

  return (
    <aside className="bill-summary">
      <div className="summary-row">
        <span>Items</span>
        <span>{itemCount}</span>
      </div>
      <div className="summary-row">
        <span>Subtotal</span>
        <span>{formatRupees(sale?.subtotal ?? 0)}</span>
      </div>
      {hasDiscount && (
        <div className="summary-row">
          <span>Discount</span>
          <span>− {formatRupees(sale.discount_amount)}</span>
        </div>
      )}
      <div className="summary-row">
        <span>Tax (GST)</span>
        <span>{formatRupees(sale?.tax_amount ?? 0)}</span>
      </div>
      <div className="summary-row summary-total">
        <span>Total</span>
        <span>{formatRupees(sale?.total ?? 0)}</span>
      </div>
    </aside>
  );
}
