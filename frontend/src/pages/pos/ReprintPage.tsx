// Find and reprint a completed bill.
import { Fragment, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getReceipt } from '../../services/api/billingApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { ReceiptOut } from '../../types/sale';
import { formatDateTime } from '../../utils/format';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';

export function ReprintPage() {
  const { t } = useTranslation();
  const { saleId } = useParams();
  // ?print=1 (straight after payment) opens the print dialog automatically; reopening a past bill doesn't.
  const [searchParams] = useSearchParams();
  const autoPrint = searchParams.get('print') === '1';
  const navigate = useNavigate();
  const [receipt, setReceipt] = useState<ReceiptOut | null>(null);
  const [error, setError] = useState('');
  const printed = useRef(false);

  useKeyboardShortcuts({ Enter: () => navigate('/pos/billing'), Escape: () => navigate('/pos/billing') });

  useEffect(() => {
    const id = Number(saleId);
    if (!Number.isInteger(id) || id < 1) {
      setError(t('receipt.invalidId'));
      return;
    }
    getReceipt(id).then(setReceipt).catch((err) => setError(getErrorMessage(err)));
  }, [saleId]);

  // The print job (and any print header the printer driver adds) is titled with the store name,
  // not the app's window title ("POS Billing"). Restored when leaving the page.
  useEffect(() => {
    if (!receipt) return;
    const previous = document.title;
    document.title = t('receipt.docTitle', { store: receipt.store_name, bill: receipt.bill_number });
    return () => { document.title = previous; };
  }, [receipt]);

  // Open the print dialog once, after the receipt has rendered.
  useEffect(() => {
    if (!receipt || !autoPrint || printed.current) return;
    printed.current = true;
    const t = window.setTimeout(() => window.print(), 100);
    return () => window.clearTimeout(t);
  }, [receipt]);

  // Item offers + manual discounts (everything except the bill offer).
  const itemSavingsPaise = receipt ? toPaise(receipt.discount_amount) - toPaise(receipt.bill_offer_discount) : 0;

  return (
    <div className="reprint-page">
      {/* No page margins: stops the browser printing its own header/footer (window title, file path, date). */}
      <style>{'@page { margin: 0; }'}</style>
      <div className="admin-header no-print">
        <h2>{t('receipt.title')}{receipt ? ` — ${receipt.store_name}` : ''}</h2>
        <div className="admin-actions">
          <button className="btn-secondary" disabled={!receipt} onClick={() => window.print()}>{t('common.print')}</button>
          <button className="btn-primary" onClick={() => navigate('/pos/billing')}>{t('receipt.newBill')}</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {!receipt && !error && <div className="loading-text">{t('common.loading')}</div>}

      {receipt && (
        <article className="receipt">
          <header className="receipt-center">
            <strong className="receipt-store">{receipt.store_name}</strong>
            {receipt.store_address && <div>{receipt.store_address}</div>}
            {receipt.store_phone && <div>{t('receipt.phone', { phone: receipt.store_phone })}</div>}
            {receipt.store_gstin && <div>{t('receipt.gstin', { gstin: receipt.store_gstin })}</div>}
            {receipt.receipt_header && <div>{receipt.receipt_header}</div>}
          </header>

          <hr />
          <div className="receipt-row"><span>{t('receipt.billNo')}</span><span>{receipt.bill_number}</span></div>
          <div className="receipt-row"><span>{t('receipt.date')}</span><span>{formatDateTime(receipt.completed_at)}</span></div>
          <div className="receipt-row">
            <span>{receipt.counter_code ? t('receipt.counter', { code: receipt.counter_code }) : ''}</span><span>{receipt.cashier_name}</span>
          </div>
          <hr />

          <table className="receipt-items">
            <thead>
              <tr><th>{t('receipt.item')}</th><th className="num">{t('receipt.qty')}</th><th className="num">{t('receipt.rate')}</th><th className="num">{t('receipt.amount')}</th></tr>
            </thead>
            <tbody>
              {receipt.items.map((i) => (
                <Fragment key={i.id}>
                  <tr>
                    <td>{i.product_name}</td>
                    <td className="num">{i.qty}</td>
                    <td className="num">{i.unit_price}</td>
                    <td className="num">{i.line_total}</td>
                  </tr>
                  {Number(i.offer_discount) > 0 && (
                    <tr>
                      <td colSpan={3}>&nbsp;&nbsp;{i.offer_name ?? t('receipt.offer')}</td>
                      <td className="num">-{i.offer_discount}</td>
                    </tr>
                  )}
                  {Number(i.manual_discount) > 0 && (
                    <tr>
                      <td colSpan={3}>&nbsp;&nbsp;{t('receipt.discount')}{i.manual_discount_reason ? ` (${i.manual_discount_reason})` : ''}</td>
                      <td className="num">-{i.manual_discount}</td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          <hr />

          <div className="receipt-row"><span>{t('receipt.subtotal')}</span><span>{formatRupees(receipt.subtotal)}</span></div>
          {itemSavingsPaise > 0 && (
            <div className="receipt-row"><span>{t('receipt.itemSavings')}</span><span>− {formatRupees(paiseToString(itemSavingsPaise))}</span></div>
          )}
          {Number(receipt.bill_offer_discount) > 0 && (
            <div className="receipt-row"><span>{receipt.bill_offer_name ?? t('receipt.billOffer')}</span><span>− {formatRupees(receipt.bill_offer_discount)}</span></div>
          )}
          <div className="receipt-row"><span>{t('receipt.gst')}</span><span>{formatRupees(receipt.tax_amount)}</span></div>
          <div className="receipt-row receipt-total"><span>{t('receipt.total')}</span><span>{formatRupees(receipt.total)}</span></div>
          {Number(receipt.discount_amount) > 0 && (
            <div className="receipt-row"><span>{t('receipt.youSaved')}</span><span>{formatRupees(receipt.discount_amount)}</span></div>
          )}
          <hr />

          {receipt.payments.map((p) => (
            <div key={p.id}>
              <div className="receipt-row">
                <span>{t('receipt.paid', { method: t(`methods.${p.method}`) })}</span>
                <span>{formatRupees(p.tendered ?? p.amount)}</span>
              </div>
              {p.change_due !== null && (
                <div className="receipt-row"><span>{t('receipt.change')}</span><span>{formatRupees(p.change_due)}</span></div>
              )}
              {p.reference && <div className="receipt-row"><span>{t('receipt.ref')}</span><span>{p.reference}</span></div>}
            </div>
          ))}

          {receipt.receipt_footer && <footer className="receipt-center receipt-footer">{receipt.receipt_footer}</footer>}
        </article>
      )}
    </div>
  );
}
