// Find and reprint a completed bill.
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getReceipt } from '../../services/api/billingApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { ReceiptOut } from '../../types/sale';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

const METHOD_LABEL: Record<string, string> = { cash: 'Cash', card: 'Card', upi: 'UPI', split: 'Split' };

export function ReprintPage() {
  const { saleId } = useParams();
  const navigate = useNavigate();
  const [receipt, setReceipt] = useState<ReceiptOut | null>(null);
  const [error, setError] = useState('');
  const printed = useRef(false);

  useKeyboardShortcuts({ Enter: () => navigate('/pos/billing'), Escape: () => navigate('/pos/billing') });

  useEffect(() => {
    const id = Number(saleId);
    if (!Number.isInteger(id) || id < 1) {
      setError('Invalid bill id.');
      return;
    }
    getReceipt(id).then(setReceipt).catch((err) => setError(getErrorMessage(err)));
  }, [saleId]);

  // Open the print dialog once, after the receipt has rendered.
  useEffect(() => {
    if (!receipt || printed.current) return;
    printed.current = true;
    const t = window.setTimeout(() => window.print(), 100);
    return () => window.clearTimeout(t);
  }, [receipt]);

  return (
    <div className="reprint-page">
      <div className="admin-header no-print">
        <h2>Receipt</h2>
        <div className="admin-actions">
          <button className="btn-secondary" disabled={!receipt} onClick={() => window.print()}>Print</button>
          <button className="btn-primary" onClick={() => navigate('/pos/billing')}>New Bill (Enter)</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {!receipt && !error && <div className="loading-text">Loading…</div>}

      {receipt && (
        <article className="receipt">
          <header className="receipt-center">
            <strong className="receipt-store">{receipt.store_name}</strong>
            {receipt.store_address && <div>{receipt.store_address}</div>}
            {receipt.store_phone && <div>Ph: {receipt.store_phone}</div>}
            {receipt.store_gstin && <div>GSTIN: {receipt.store_gstin}</div>}
          </header>

          <hr />
          <div className="receipt-row"><span>Bill No</span><span>{receipt.bill_number}</span></div>
          <div className="receipt-row"><span>Date</span><span>{formatDateTime(receipt.completed_at)}</span></div>
          <div className="receipt-row">
            <span>{receipt.counter_code ? `Counter ${receipt.counter_code}` : ''}</span><span>{receipt.cashier_name}</span>
          </div>
          <hr />

          <table className="receipt-items">
            <thead>
              <tr><th>Item</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">Amt</th></tr>
            </thead>
            <tbody>
              {receipt.items.map((i) => (
                <tr key={i.id}>
                  <td>{i.product_name}</td>
                  <td className="num">{i.qty}</td>
                  <td className="num">{i.unit_price}</td>
                  <td className="num">{i.line_total}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <hr />

          <div className="receipt-row"><span>Subtotal</span><span>{formatRupees(receipt.subtotal)}</span></div>
          {Number(receipt.discount_amount) > 0 && (
            <div className="receipt-row"><span>Discount</span><span>− {formatRupees(receipt.discount_amount)}</span></div>
          )}
          <div className="receipt-row"><span>GST</span><span>{formatRupees(receipt.tax_amount)}</span></div>
          <div className="receipt-row receipt-total"><span>TOTAL</span><span>{formatRupees(receipt.total)}</span></div>
          <hr />

          {receipt.payments.map((p) => (
            <div key={p.id}>
              <div className="receipt-row">
                <span>Paid ({METHOD_LABEL[p.method] ?? p.method})</span>
                <span>{formatRupees(p.tendered ?? p.amount)}</span>
              </div>
              {p.change_due !== null && (
                <div className="receipt-row"><span>Change</span><span>{formatRupees(p.change_due)}</span></div>
              )}
              {p.reference && <div className="receipt-row"><span>Ref</span><span>{p.reference}</span></div>}
            </div>
          ))}

          <footer className="receipt-center receipt-footer">Thank you! Visit again.</footer>
        </article>
      )}
    </div>
  );
}
