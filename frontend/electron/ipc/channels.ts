// IPC channel names shared by main.ts handlers and preload.ts.
export const IPC = {
  getCounterConfig: 'config:get',
  saveCounterConfig: 'config:save',
  printReceipt: 'printer:print',
  listPrinters: 'printer:list',
  openDrawer: 'drawer:open',
  getMachineId: 'license:get-machine-id',
  checkLicense: 'license:check',
  activateLicense: 'license:activate',
} as const;
