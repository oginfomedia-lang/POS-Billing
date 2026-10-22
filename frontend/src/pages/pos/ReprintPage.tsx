// Show and (re)print a completed bill. Prints silently on the counter's printer (Electron).
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { IconArrowLeft, IconDashboard } from '../../components/common/Icons';
import { EbillBar } from '../../components/pos/EbillBar';
import { ReceiptView } from '../../components/pos/ReceiptView';
import { useAuth } from '../../hooks/useAuth';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { useReceiptPrint } from '../../hooks/useReceiptPrint';
import { getReceipt } from '../../services/api/billingApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { ReceiptOut } from '../../types/sale';

export function ReprintPage() {
  const { t } = useTranslation();
  const { saleId } = useParams();
  // ?print=1 (straight after payment) prints automatically; reopening a past bill doesn't.
  const [searchParams] = useSearchParams();
  const autoPrint = searchParams.get('print') === '1';
  // ?from=shift: opened from the cashier's shift bill list.
  const fromShift = searchParams.get('from') === 'shift';
  const fromBills = searchParams.get('from') === 'bills';
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin' || user?.role === 'manager';
  const [receipt, setReceipt] = useState<ReceiptOut | null>(null);
  const [error, setError] = useState('');
  const { print, printing, printError } = useReceiptPrint(receipt !== null, autoPrint);

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
  // not the app's window title ("LiteRetail"). Restored when leaving the page.
  useEffect(() => {
    if (!receipt) return;
    const previous = document.title;
    document.title = t('receipt.docTitle', { store: receipt.store_name, bill: receipt.bill_number });
    return () => { document.title = previous; };
  }, [receipt]);

  return (
    <div className="reprint-page">
      {/* No page margins: stops the browser printing its own header/footer (window title, file path, date). */}
      <style>{'@page { margin: 0; }'}</style>
      <div className="admin-header no-print">
        <h2>{t('receipt.title')}{receipt ? ` — ${receipt.store_name}` : ''}</h2>
        <div className="admin-actions">
          {fromShift && (
            <button className="btn-secondary btn-icon" onClick={() => navigate('/pos/shift/bills')}>
              <IconArrowLeft size={15} />
              <span>{t('receipt.backToShiftBills')}</span>
            </button>
          )}
          {fromBills && (
            <button className="btn-secondary btn-icon" onClick={() => navigate(-1)}>
              <IconArrowLeft size={15} />
              <span>{t('bills.backToBills')}</span>
            </button>
          )}
          {isAdmin && (
            <button className="btn-secondary btn-icon" onClick={() => navigate('/admin')}>
              <IconDashboard size={15} />
              <span>{t('receipt.backToDashboard')}</span>
            </button>
          )}
          <button className="btn-secondary" disabled={!receipt || printing} onClick={print}>
            {printing ? t('receipt.printing') : t('common.print')}
          </button>
          <button className="btn-primary" onClick={() => navigate('/pos/billing')}>{t('receipt.newBill')}</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {printError && <div className="page-error no-print">{t('receipt.printFailed', { error: printError })}</div>}
      {receipt && <EbillBar receipt={receipt} printFailed={!!printError} />}
      {!receipt && !error && <div className="loading-text">{t('common.loading')}</div>}

      {receipt && <ReceiptView receipt={receipt} />}
    </div>
  );
}
