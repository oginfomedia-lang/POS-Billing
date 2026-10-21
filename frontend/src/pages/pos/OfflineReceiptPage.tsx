// An offline bill's receipt, from the copy saved on this PC. Prints by itself straight after the sale (?print=1).
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ReceiptView } from '../../components/pos/ReceiptView';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { useReceiptPrint } from '../../hooks/useReceiptPrint';
import { toReceipt } from '../../offline/bill';
import type { OfflineBill } from '../../offline/types';
import type { ReceiptOut } from '../../types/sale';

export function OfflineReceiptPage() {
  const { t } = useTranslation();
  const { offlineId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [bill, setBill] = useState<OfflineBill | null>(null);
  const [receipt, setReceipt] = useState<ReceiptOut | null>(null);
  const [missing, setMissing] = useState(false);
  const { print, printing, printError } = useReceiptPrint(receipt !== null, searchParams.get('print') === '1');

  useKeyboardShortcuts({ Enter: () => navigate('/pos/offline'), Escape: () => navigate('/pos/offline') });

  useEffect(() => {
    if (!offlineId || !window.posBridge?.offline) { setMissing(true); return; }
    window.posBridge.offline.getBill(offlineId).then((found) => {
      if (!found) { setMissing(true); return; }
      const b = found as OfflineBill;
      setBill(b);
      setReceipt(toReceipt(b));
    }).catch(() => setMissing(true));
  }, [offlineId]);

  useEffect(() => {
    if (!receipt) return;
    const previous = document.title;
    document.title = t('receipt.docTitle', { store: receipt.store_name, bill: receipt.bill_number });
    return () => { document.title = previous; };
  }, [receipt]);

  return (
    <div className="reprint-page">
      <style>{'@page { margin: 0; }'}</style>
      <div className="admin-header no-print">
        <h2>{t('offline.receiptTitle')}{receipt ? ` — ${receipt.bill_number}` : ''}</h2>
        <div className="admin-actions">
          <button className="btn-secondary" disabled={!receipt || printing} onClick={print}>
            {printing ? t('receipt.printing') : t('common.print')}
          </button>
          <button className="btn-primary" onClick={() => navigate('/pos/offline')}>{t('offline.newBill')}</button>
        </div>
      </div>
      {missing && <div className="page-error">{t('offline.billNotFound')}</div>}
      {printError && <div className="page-error no-print">{t('receipt.printFailed', { error: printError })}</div>}
      {bill && (
        <div className="notice-bar notice-info no-print">
          {bill.synced_sale_id ? t('offline.receiptSynced') : t('offline.receiptNote')}
        </div>
      )}
      {receipt && <ReceiptView receipt={receipt} />}
    </div>
  );
}
