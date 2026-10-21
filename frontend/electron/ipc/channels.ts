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
} as const;
