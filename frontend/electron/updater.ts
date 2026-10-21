// Automatic updates (installed app only). Every PC updates from the Main PC's server, <apiUrl>/updates, which
// copies new versions from the vendor (backend services/update_mirror_service.py): counters need no internet.
// A new version downloads in the background and installs when the app is closed, or at once from the banner.
import { BrowserWindow, app, ipcMain } from 'electron';
import { autoUpdater } from 'electron-updater';
import type { CounterConfig } from './config/counterConfig';
import { IPC } from './ipc/channels';

const CHECK_EVERY_MS = 2 * 60 * 60 * 1000; // 2 hours

export interface UpdateInfo {
  version: string;
}

let ready: UpdateInfo | null = null;

export function initAutoUpdater(config: CounterConfig): void {
  ipcMain.handle(IPC.getUpdateReady, () => ready);
  // Silent install, then start the app again. The installer stops and restarts the server service itself.
  ipcMain.handle(IPC.installUpdate, () => {
    if (ready) autoUpdater.quitAndInstall(true, true);
  });
  if (!app.isPackaged) return;

  autoUpdater.setFeedURL({ provider: 'generic', url: `${config.apiUrl.replace(/\/+$/, '')}/updates` });
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true; // closing the app at the end of the day installs it
  autoUpdater.logger = console;

  autoUpdater.on('update-downloaded', (info) => {
    ready = { version: info.version };
    for (const win of BrowserWindow.getAllWindows()) win.webContents.send(IPC.updateReady, ready);
  });
  // No server, no update yet, or a bad download: try again at the next check. Never bothers the cashier.
  autoUpdater.on('error', (err) => console.warn('Update check failed:', err?.message ?? err));

  const check = () => autoUpdater.checkForUpdates().catch(() => undefined);
  setTimeout(check, 60_000); // after start-up, once the server is surely up
  setInterval(check, CHECK_EVERY_MS);
}
