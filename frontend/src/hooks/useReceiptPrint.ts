// Printing for receipt pages: optional automatic print once the receipt is on screen, a manual
// print() for the Print button, and the error to show when the printer fails.
import { useEffect, useRef, useState } from 'react';
import { autoPrintEnabled, printReceipt } from '../services/hardware/printerService';

/**
 * @param ready  the receipt has rendered
 * @param auto   print by itself (e.g. straight after a sale) — skipped when the counter has auto-print off
 */
export function useReceiptPrint(ready: boolean, auto: boolean) {
  const [printing, setPrinting] = useState(false);
  const [printError, setPrintError] = useState('');
  const printed = useRef(false);

  async function print() {
    setPrinting(true);
    setPrintError('');
    const result = await printReceipt();
    setPrinting(false);
    if (!result.ok) setPrintError(result.error || 'Printing failed.');
  }

  useEffect(() => {
    if (!ready || !auto || printed.current || !autoPrintEnabled()) return;
    // Mark as printed only when the timer fires: React StrictMode runs effects twice in development,
    // and the first run's timer is cleared.
    const timer = window.setTimeout(() => {
      printed.current = true;
      print();
    }, 150);
    return () => window.clearTimeout(timer);
  }, [ready, auto]);

  return { print, printing, printError };
}
