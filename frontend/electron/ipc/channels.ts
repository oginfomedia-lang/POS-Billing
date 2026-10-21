// IPC channel names shared by main.ts handlers and preload.ts.
export const IPC = {
  getCounterConfig: 'config:get',
  saveCounterConfig: 'config:save',
  printReceipt: 'printer:print',
  listPrinters: 'printer:list',
  openDrawer: 'drawer:open',
  getUpdateReady: 'update:get-ready',
  installUpdate: 'update:install',
  updateReady: 'update:ready', // main -> renderer event
  offlineSaveCatalog: 'offline:save-catalog',
  offlineLoadCatalog: 'offline:load-catalog',
  offlineNextBillNumber: 'offline:next-bill-number',
  offlineQueueBill: 'offline:queue-bill',
  offlineListQueue: 'offline:list-queue',
  offlineGetBill: 'offline:get-bill',
  offlineMarkSynced: 'offline:mark-synced',
  offlineMarkFailed: 'offline:mark-failed',
} as const;
