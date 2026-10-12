// WhatsApp e-bill status on the bill screen (never printed), with "Send on WhatsApp" — also to a number
// typed in here, e.g. when the printer isn't working and the customer wasn't added to the bill.
import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getReceipt, sendEbill } from '../../services/api/billingApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { EbillStatus, ReceiptOut } from '../../types/sale';

const POLL_MS = 3000;
const POLL_TRIES = 5;

interface Props {
  receipt: ReceiptOut;
  /** Printing failed: offer WhatsApp more prominently. */
  printFailed: boolean;
}

export function EbillBar({ receipt, printFailed }: Props) {
  const { t } = useTranslation();
  const [ebill, setEbill] = useState<EbillStatus | null>(receipt.ebill);
  const [mobile, setMobile] = useState('');
  const [askMobile, setAskMobile] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { setEbill(receipt.ebill); }, [receipt]);

  // Straight after payment the server is still sending: check back a few times.
  useEffect(() => {
    if (ebill?.status !== 'pending') return;
    let tries = 0;
    const timer = window.setInterval(() => {
      tries += 1;
      getReceipt(receipt.sale_id)
        .then((r) => { if (r.ebill) setEbill(r.ebill); })
        .catch(() => undefined);
      if (tries >= POLL_TRIES) window.clearInterval(timer);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [ebill?.status, receipt.sale_id]);

  // No number on the bill and none typed yet: ask for it first.
  const needsMobile = !receipt.customer_mobile && !mobile;

  async function send(event?: FormEvent) {
    event?.preventDefault();
    if (needsMobile) {
      setAskMobile(true);
      return;
    }
    setSending(true);
    setError('');
    try {
      setEbill(await sendEbill(receipt.sale_id, mobile || undefined));
      setAskMobile(false);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSending(false);
    }
  }

  const button = (
    <button className={printFailed ? 'btn-primary error-retry' : 'btn-secondary error-retry'} type="submit" disabled={sending}>
      {sending ? t('receipt.ebillSending') : ebill?.status === 'sent' ? t('receipt.ebillResend') : t('receipt.ebillSend')}
    </button>
  );

  let className = 'notice-bar notice-info';
  let text = printFailed ? t('receipt.ebillPrinterDown') : '';
  if (ebill?.status === 'sent') {
    className = 'notice-bar';
    text = t('receipt.ebillSent', { mobile: ebill.recipient });
  } else if (ebill?.status === 'pending') {
    text = t('receipt.ebillPending', { mobile: ebill.recipient });
  } else if (ebill?.status === 'failed') {
    className = 'page-error';
    text = t('receipt.ebillFailed', { mobile: ebill.recipient, error: ebill.error ?? '' });
  }

  return (
    <form className={`${className} no-print`} onSubmit={send}>
      <span>{text}</span>
      {(askMobile || (mobile && !receipt.customer_mobile)) && (
        <input
          className="field-input filter-input"
          type="tel"
          inputMode="numeric"
          maxLength={14}
          autoFocus
          placeholder={t('receipt.ebillMobile')}
          aria-label={t('receipt.ebillMobile')}
          value={mobile}
          onChange={(e) => setMobile(e.target.value)}
          onKeyDown={(e) => e.stopPropagation() /* Enter here sends, it doesn't start a new bill */}
        />
      )}
      {button}
      {error && <span className="form-error">{error}</span>}
    </form>
  );
}
