// IPC handlers for reading counter configuration.
import { ipcMain } from 'electron';
import { loadCounterConfig } from '../config/counterConfig';
import { IPC } from './channels';

export function registerConfigHandlers(): void {
  ipcMain.handle(IPC.getCounterConfig, () => loadCounterConfig());
}
