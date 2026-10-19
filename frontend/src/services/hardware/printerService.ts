// Receipt printing and cash drawer for the React screens.
// In the Electron app this goes to window.posBridge (silent print to the counter's printer);
// in a plain browser (e.g. testing the UI with `vite`) it falls back to the browser print dialog.
import type { PrintErrorCode } from '../../../electron/ipc/printerHandlers';
import i18n from '../../i18n';
import { useCounterStore } from '../../store/counterStore';

export interface HardwareResult {
  ok: boolean;
  error?: string;
  code?: PrintErrorCode;
  printer?: string;
}

/** Fills `error` with a message that says what to do, in the screen's language, when the app knows why. */
function explain(result: HardwareResult): HardwareResult {
  if (result.ok || !result.code) return result;
  const key = `printer.errors.${result.code}` as const;
  return { ...result, error: i18n.t(key, { name: result.printer ?? '' }) };
}

function bridge() {
  return typeof window !== 'undefined' ? window.posBridge : undefined;
}

/** Prints the receipt currently on screen. Never throws: check `ok` / `error`. */
export async function printReceipt(): Promise<HardwareResult> {
  const b = bridge();
  if (!b?.printReceipt) {
    window.print();
    return { ok: true };
  }
  try {
    return explain(await b.printReceipt());
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

/** Opens the cash drawer. Fire-and-forget: a drawer problem must never block a sale or refund. */
export async function openDrawer(): Promise<HardwareResult> {
  const b = bridge();
  if (!b?.openDrawer) return { ok: true };
  try {
    const result = await b.openDrawer();
    if (!result.ok) console.warn('Cash drawer:', result.error);
    return result;
  } catch (err) {
    console.warn('Cash drawer:', err);
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

/** Whether receipts should print by themselves after a sale/return (counter.json `autoPrint`). */
export function autoPrintEnabled(): boolean {
  return useCounterStore.getState().config?.autoPrint ?? true;
}

/** True inside the Electron app (printer settings exist only there). */
export function hasPrinterBridge(): boolean {
  return Boolean(bridge()?.printReceipt);
}
