// Card / UPI through Razorpay: start on open, poll until paid, cancel on close.
// The amount always comes from the server (bill total), never from this screen.
import { useEffect, useRef, useState } from 'react';
import { cancelPayment, checkPayment, startPayment } from '../../services/api/billingApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { DigitalMethod, PaymentIntentOut, SaleOut } from '../../types/sale';
import { formatRupees } from '../../utils/money';

const POLL_MS = 2000;

interface Props {
  saleId: number;
  method: DigitalMethod;
  total: string;
  /** Razorpay confirmed the money and the backend completed the bill. */
  onPaid: (sale: SaleOut) => void;
}

export function DigitalPaymentPanel({ saleId, method, total, onPaid }: Props) {
  const [intent, setIntent] = useState<PaymentIntentOut | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0); // bumped by "Try again"
  const onPaidRef = useRef(onPaid);
  onPaidRef.current = onPaid;

  useEffect(() => {
    let stopped = false;
    let current: PaymentIntentOut | null = null;
    let timer: number | undefined;
    setIntent(null);
    setError('');

    async function poll() {
      if (stopped || !current) return;
      try {
        const next = await checkPayment(current.id);
        if (stopped) return;
        current = next;
        setIntent(next);
        setError('');
        if (next.status === 'paid' && next.sale) {
          onPaidRef.current(next.sale);
          return;
        }
        if (next.status !== 'pending') return; // failed / cancelled: wait for "Try again"
      } catch (err) {
        // Network blip or e.g. stock problem after payment: show it, keep checking.
        if (!stopped) setError(getErrorMessage(err));
      }
      timer = window.setTimeout(poll, POLL_MS);
    }

    startPayment(saleId, method)
      .then((created) => {
        if (stopped) {
          cancelPayment(created.id).catch(() => {});
          return;
        }
        current = created;
        setIntent(created);
        timer = window.setTimeout(poll, POLL_MS);
      })
      .catch((err) => {
        if (!stopped) setError(getErrorMessage(err));
      });

    return () => {
      // Dialog closed or tab switched: kill the QR / card-machine request so it can't be paid later.
      stopped = true;
      window.clearTimeout(timer);
      if (current?.status === 'pending') cancelPayment(current.id).catch(() => {});
    };
  }, [saleId, method, attempt]);

  const pending = intent?.status === 'pending';
  const ended = intent?.status === 'failed' || intent?.status === 'cancelled';
  const startFailed = !intent && !!error;

  return (
    <div className="digital-payment-section">
      {error && <div className="form-error">{error}</div>}

      {!intent && !error && (
        <p className="digital-wait">{method === 'upi' ? 'Creating UPI QR…' : 'Sending amount to card machine…'}</p>
      )}

      {pending && method === 'upi' && intent?.qr_image_url && (
        <div className="digital-pay-box">
          <img src={intent.qr_image_url} alt="UPI QR code" className="upi-qr-img" />
          <strong className="digital-pay-amount">{formatRupees(total)}</strong>
          <span className="digital-wait">
            Ask the customer to scan with any UPI app. The bill closes by itself once paid.
          </span>
        </div>
      )}

      {pending && method === 'card' && (
        <div className="digital-pay-box">
          <strong className="digital-pay-amount">{formatRupees(total)}</strong>
          <span className="digital-wait">
            Amount sent to the card machine. Ask the customer to tap, insert or swipe the card and enter the PIN.
          </span>
        </div>
      )}

      {pending && <p className="digital-wait digital-pulse">Waiting for payment…</p>}

      {intent?.status === 'paid' && <p className="digital-ok">Payment received. Printing bill…</p>}

      {(ended || startFailed) && (
        <div className="digital-retry">
          {ended && <p className="form-error">{intent?.failure_reason || 'Payment was not completed.'}</p>}
          <button type="button" className="btn-primary" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
