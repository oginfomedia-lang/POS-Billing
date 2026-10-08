// IPC handlers for reading and saving counter configuration.
import { ipcMain } from 'electron';
import { loadCounterConfig, saveCounterConfig, type PrinterSettings } from '../config/counterConfig';
import { IPC } from './channels';

export function registerConfigHandlers(): void {
  ipcMain.handle(IPC.getCounterConfig, () => loadCounterConfig());
  // Only printer settings can be changed from the screen; counterCode / apiUrl stay installer-only.
  ipcMain.handle(IPC.saveCounterConfig, (_event, changes: Partial<PrinterSettings>) =>
    saveCounterConfig(changes ?? {}),
  );
}
