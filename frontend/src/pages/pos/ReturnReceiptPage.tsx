// Return slip (credit note): shown and printed after a return; can be reopened by id.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { useReceiptPrint } from '../../hooks/useReceiptPrint';
import { getErrorMessage } from '../../services/api/httpClient';
import { getReturn } from '../../services/api/returnApi';
import type { ReturnOut } from '../../types/returns';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

export function ReturnReceiptPage() {
  const { t } = useTranslation();
  const { returnId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [ret, setRet] = useState<ReturnOut | null>(null);
  const [error, setError] = useState('');
  const { print, printing, printError } = useReceiptPrint(ret !== null, searchParams.get('print') === '1');

  useKeyboardShortcuts({ Enter: () => navigate('/pos/billing'), Escape: () => navigate('/pos/billing') });

  useEffect(() => {
    const id = Number(returnId);
    if (!Number.isInteger(id) || id < 1) {
      setError(t('receipt.invalidId'));
      return;
    }
    getReturn(id).then(setRet).catch((err) => setError(getErrorMessage(err)));
  }, [returnId]);

  // Print job title = store + return number (not the app window title).
  useEffect(() => {
    if (!ret) return;
    const previous = document.title;
    document.title = t('returns.docTitle', { store: ret.store_name, number: ret.return_number });
    return () => { document.title = previous; };
  }, [ret]);

  return (
    <div className="reprint-page">
      <style>{'@page { margin: 0; }'}</style>
      <div className="admin-header no-print">
        <h2>{t('returns.slipTitle')}</h2>
        <div className="admin-actions">
          <button className="btn-secondary" disabled={!ret || printing} onClick={print}>
            {printing ? t('receipt.printing') : t('common.print')}
          </button>
          <button className="btn-secondary" onClick={() => navigate('/pos/returns')}>{t('returns.another')}</button>
          <button className="btn-primary" onClick={() => navigate('/pos/billing')}>{t('receipt.newBill')}</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {printError && <div className="page-error no-print">{t('receipt.printFailed', { error: printError })}</div>}
      {!ret && !error && <div className="loading-text">{t('common.loading')}</div>}

      {ret && (
        <article className="receipt">
          <header className="receipt-center">
            <strong className="receipt-store">{ret.store_name}</strong>
            {ret.store_address && <div>{ret.store_address}</div>}
            {ret.store_phone && <div>{t('receipt.phone', { phone: ret.store_phone })}</div>}
            {ret.store_gstin && <div>{t('receipt.gstin', { gstin: ret.store_gstin })}</div>}
            <div className="receipt-doc-title">{t('returns.creditNote')}</div>
          </header>

          <hr />
          <div className="receipt-row"><span>{t('returns.returnNo')}</span><span>{ret.return_number}</span></div>
          <div className="receipt-row"><span>{t('receipt.date')}</span><span>{formatDateTime(ret.created_at)}</span></div>
          <div className="receipt-row"><span>{t('returns.originalBill')}</span><span>{ret.bill_number}</span></div>
          <div className="receipt-row"><span>{t('returns.billDate')}</span><span>{formatDateTime(ret.bill_date)}</span></div>
          <div className="receipt-row">
            <span>{ret.counter_code ? t('receipt.counter', { code: ret.counter_code }) : ''}</span><span>{ret.cashier_name}</span>
          </div>
          {ret.customer_mobile && (
            <div className="receipt-row"><span>{t('receipt.customer')}</span><span>{ret.customer_mobile}</span></div>
          )}
          <hr />

          <table className="receipt-items">
            <thead>
              <tr><th>{t('receipt.item')}</th><th className="num">{t('receipt.qty')}</th><th className="num">{t('receipt.amount')}</th></tr>
            </thead>
            <tbody>
              {ret.items.map((i, idx) => (
                <tr key={idx}>
                  <td>
                    {i.product_name}
                    {!i.restocked && <span className="receipt-small"> ({t('returns.damaged')})</span>}
                  </td>
                  <td className="num">{i.qty}</td>
                  <td className="num">{i.refund_amount}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <hr />

          <div className="receipt-row"><span>{t('receipt.subtotal')}</span><span>{formatRupees(ret.subtotal)}</span></div>
          {Number(ret.discount_amount) > 0 && (
            <div className="receipt-row"><span>{t('returns.lessDiscount')}</span><span>− {formatRupees(ret.discount_amount)}</span></div>
          )}
          <div className="receipt-row receipt-total">
            <span>{t('returns.cashRefunded')}</span><span>{formatRupees(ret.refund_amount)}</span>
          </div>
          <hr />

          <div className="receipt-row"><span>{t('returns.reason')}</span><span>{ret.reason}</span></div>
          <div className="receipt-row"><span>{t('returns.approvedBy')}</span><span>{ret.approved_by_name}</span></div>
          {ret.receipt_footer && <footer className="receipt-center receipt-footer">{ret.receipt_footer}</footer>}
        </article>
      )}
    </div>
  );
}
