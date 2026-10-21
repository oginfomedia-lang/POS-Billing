// Exposes the safe window.posBridge API to React.
// React never gets Node.js or hardware access directly; only these functions.
import { contextBridge, ipcRenderer } from 'electron';
import type { CounterConfig, PrinterSettings } from './config/counterConfig';
import { IPC } from './ipc/channels';
import type { HardwareResult, PrinterListItem } from './ipc/printerHandlers';
import type { UpdateInfo } from './updater';

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
  /** A downloaded update waiting to be installed, or null. */
  getUpdateReady: (): Promise<UpdateInfo | null> => ipcRenderer.invoke(IPC.getUpdateReady),
  /** Called when an update has been downloaded. Returns a function that stops listening. */
  onUpdateReady: (callback: (info: UpdateInfo) => void): (() => void) => {
    const listener = (_event: unknown, info: UpdateInfo) => callback(info);
    ipcRenderer.on(IPC.updateReady, listener);
    return () => ipcRenderer.removeListener(IPC.updateReady, listener);
  },
  /** Closes the app, installs the update silently and starts the new version. */
  installUpdate: (): Promise<void> => ipcRenderer.invoke(IPC.installUpdate),
};

export type PosBridge = typeof posBridge;

contextBridge.exposeInMainWorld('posBridge', posBridge);
