// Exposes the safe window.posBridge API to React.
// React never gets Node.js or hardware access directly; only these functions.
import { contextBridge, ipcRenderer } from 'electron';
import type { CounterConfig, PrinterSettings } from './config/counterConfig';
import { IPC } from './ipc/channels';
import type { HardwareResult, PrinterListItem } from './ipc/printerHandlers';

const posBridge = {
  getCounterConfig: (): Promise<CounterConfig> => ipcRenderer.invoke(IPC.getCounterConfig),
  /** Saves this counter's printer settings into counter.json; returns the new config. */
  saveCounterConfig: (changes: Partial<PrinterSettings>): Promise<CounterConfig> =>
    ipcRenderer.invoke(IPC.saveCounterConfig, changes),
  /** Prints the current page silently on this counter's printer (receipt pages only). */
  printReceipt: (): Promise<HardwareResult> => ipcRenderer.invoke(IPC.printReceipt),
  listPrinters: (): Promise<PrinterListItem[]> => ipcRenderer.invoke(IPC.listPrinters),
  /** Kicks the cash drawer through the receipt printer (no-op when switched off). */
  openDrawer: (): Promise<HardwareResult> => ipcRenderer.invoke(IPC.openDrawer),
};

export type PosBridge = typeof posBridge;

contextBridge.exposeInMainWorld('posBridge', posBridge);
