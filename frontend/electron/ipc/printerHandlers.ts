// IPC handlers for printing and opening the cash drawer.
import { ipcMain, type WebContents } from 'electron';
import { loadCounterConfig } from '../config/counterConfig';
import { openDrawer } from '../hardware/cashDrawer';
import { IPC } from './channels';

/** Result of a hardware action; never throws across IPC, so the screen can show `error`. */
export interface HardwareResult {
  ok: boolean;
  error?: string;
}

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

function printSilently(contents: WebContents): Promise<HardwareResult> {
  const { printerName } = loadCounterConfig();
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
