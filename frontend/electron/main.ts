// Creates the POS window and registers IPC handlers.
import { join } from 'node:path';
import { app, BrowserWindow } from 'electron';
import { loadCounterConfig } from './config/counterConfig';
import { registerConfigHandlers } from './ipc/configHandlers';
import { registerPrinterHandlers } from './ipc/printerHandlers';

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1366,
    height: 768,
    show: false,
    autoHideMenuBar: true,
    title: 'LiteRetailer',
    webPreferences: {
      preload: join(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.once('ready-to-show', () => {
    win.maximize();
    // DevTools only while developing, never in the installed app at the counter.
    if (process.env.ELECTRON_RENDERER_URL) win.webContents.openDevTools();
    win.show();
  });

  // The POS never opens other windows or navigates away from the app.
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (event) => event.preventDefault());

  const devServerUrl = process.env.ELECTRON_RENDERER_URL;
  if (devServerUrl) {
    win.loadURL(devServerUrl);
  } else {
    // Right after Windows starts, the LiteRetailer Server service may still be starting: show a
    // "starting" screen until it answers instead of a login page that can't reach it.
    win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(STARTING_PAGE)}`);
    waitForServer().finally(() => win.loadFile(join(__dirname, '../renderer/index.html')));
  }
}

const STARTING_PAGE = `<!doctype html><title>LiteRetailer</title>
<body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;font-family:Segoe UI,sans-serif;background:#f8fafc;color:#334155">
<div style="text-align:center"><h2 style="margin:0 0 8px">LiteRetailer</h2><p>Connecting to the server…</p></div></body>`;

/** Polls <apiUrl>/health for up to 60 s. Resolves either way; the login screen reports a server that stays down. */
async function waitForServer(): Promise<void> {
  let apiUrl: string;
  try {
    apiUrl = loadCounterConfig().apiUrl.replace(/\/+$/, '');
  } catch {
    return;
  }
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${apiUrl}/health`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
}

// One POS app per counter PC.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const [win] = BrowserWindow.getAllWindows();
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  app.whenReady().then(() => {
    registerConfigHandlers();
    registerPrinterHandlers();
    createWindow();
  });

  app.on('window-all-closed', () => app.quit());
}
