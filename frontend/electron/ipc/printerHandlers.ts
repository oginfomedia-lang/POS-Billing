// IPC handlers for printing and opening the cash drawer.
import { ipcMain, type WebContents } from 'electron';
import { loadCounterConfig } from '../config/counterConfig';
import { openDrawer } from '../hardware/cashDrawer';
import { IPC } from './channels';

/** Why a receipt didn't print; the screen turns it into a message with what to do (printer.errors.*). */
export type PrintErrorCode = 'noPrinters' | 'noPrinterSet' | 'printerNotFound' | 'virtualPrinter' | 'cancelled';

/** Result of a hardware action; never throws across IPC, so the screen can show `error`. */
export interface HardwareResult {
  ok: boolean;
  error?: string;
  code?: PrintErrorCode;
  /** The printer the code is about. */
  printer?: string;
}

/** Windows "printers" that save a file instead of printing: a silent print to them is always cancelled. */
const VIRTUAL_PRINTER = /pdf|xps|onenote|fax|send to/i;

export interface PrinterListItem {
  name: string;
  displayName: string;
}

export function registerPrinterHandlers(): void {
  // Prints what the calling window shows (the receipt page's @media print CSS hides everything else).
  ipcMain.handle(IPC.printReceipt, (event): Promise<HardwareResult> => printSilently(event.sender));

  ipcMain.handle(IPC.listPrinters, async (event): Promise<PrinterListItem[]> => {
    const printers = await event.sender.getPrintersAsync();
    return printers.map((p) => ({ name: p.name, displayName: p.displayName || p.name }));
  });

  ipcMain.handle(IPC.openDrawer, async (): Promise<HardwareResult> => {
    try {
      await openDrawer(loadCounterConfig());
      return { ok: true };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  });
}

async function printSilently(contents: WebContents): Promise<HardwareResult> {
  const { printerName } = loadCounterConfig();

  // Catch the usual set-up problems before Windows cancels the job with a bare "Print job canceled".
  const installed = await contents.getPrintersAsync().catch(() => null);
  if (installed) {
    if (installed.length === 0) return { ok: false, code: 'noPrinters' };
    if (printerName && !installed.some((p) => p.name === printerName)) {
      return { ok: false, code: 'printerNotFound', printer: printerName };
    }
    if (printerName && VIRTUAL_PRINTER.test(printerName)) {
      return { ok: false, code: 'virtualPrinter', printer: printerName };
    }
  }

  const result = await printToDevice(contents, printerName);
  if (result.ok || !/cancel/i.test(result.error ?? '')) return result;
  // No printer chosen: the job went to the Windows default, which is usually "Microsoft Print to PDF".
  return printerName ? { ok: false, code: 'cancelled', printer: printerName } : { ok: false, code: 'noPrinterSet' };
}

function printToDevice(contents: WebContents, printerName: string): Promise<HardwareResult> {
  return new Promise((resolve) => {
    contents.print(
      {
        silent: true,
        deviceName: printerName || undefined, // undefined = Windows default printer
        printBackground: false,
        margins: { marginType: 'none' },
      },
      (success, failureReason) =>
        resolve(success ? { ok: true } : { ok: false, error: failureReason || 'Printing failed.' }),
    );
  });
}
