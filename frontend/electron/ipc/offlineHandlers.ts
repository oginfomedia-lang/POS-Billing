// IPC handlers for offline billing files (electron/offline/offlineStore.ts).
import { ipcMain } from 'electron';
import {
  getBill,
  listQueue,
  loadCatalog,
  markFailed,
  markSynced,
  nextBillNumber,
  pruneSynced,
  queueBill,
  saveCatalog,
} from '../offline/offlineStore';
import { IPC } from './channels';

export function registerOfflineHandlers(): void {
  try {
    pruneSynced();
  } catch (err) {
    console.warn('Could not prune old offline bills:', err);
  }
  ipcMain.handle(IPC.offlineSaveCatalog, (_e, storeId: number, catalog: unknown) => saveCatalog(storeId, catalog));
  ipcMain.handle(IPC.offlineLoadCatalog, (_e, storeId: number) => loadCatalog(storeId));
  ipcMain.handle(IPC.offlineNextBillNumber, (_e, counterCode: string) => nextBillNumber(String(counterCode)));
  ipcMain.handle(IPC.offlineQueueBill, (_e, bill: { offline_id: string }) => queueBill(bill));
  ipcMain.handle(IPC.offlineListQueue, () => listQueue());
  ipcMain.handle(IPC.offlineGetBill, (_e, offlineId: string) => getBill(String(offlineId)));
  ipcMain.handle(IPC.offlineMarkSynced, (_e, offlineId: string, saleId: number) => markSynced(String(offlineId), Number(saleId)));
  ipcMain.handle(IPC.offlineMarkFailed, (_e, offlineId: string, error: string) => markFailed(String(offlineId), String(error)));
}
