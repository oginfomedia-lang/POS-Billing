// Things that open outside the app window. The window itself never opens new windows or navigates away (main.ts),
// so links and files go through here, each kept to a narrow, safe shape:
// - WhatsApp: only wa.me links (e.g. a purchase order for a supplier).
// - Documents: a stored supplier bill / payment receipt (PDF or image) opens in Windows' own viewer.
import { randomUUID } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ipcMain, shell } from 'electron';
import { IPC } from './channels';

const WHATSAPP = /^https:\/\/wa\.me\/\d{10,15}(\?text=[^\s]*)?$/;

// The file types the server accepts for documents (backend upload_service.ALLOWED_MIME_TYPES). The extension is
// chosen here from the type, never taken from the file's name, so nothing runnable (.exe, .bat) can be opened.
const DOC_EXTENSIONS: Record<string, string> = {
  'application/pdf': 'pdf',
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/gif': 'gif',
  'image/webp': 'webp',
  'image/tiff': 'tif',
};
const MAX_DOC_BYTES = 25 * 1024 * 1024;

export function registerShellHandlers(): void {
  ipcMain.handle(IPC.openWhatsApp, async (_event, url: unknown): Promise<boolean> => {
    if (typeof url !== 'string' || !WHATSAPP.test(url)) return false;
    await shell.openExternal(url);
    return true;
  });

  /** Saves the document to a temporary folder and opens it. Returns '' when opened, else the reason. */
  ipcMain.handle(IPC.openDocument, async (_event, data: unknown, mimeType: unknown): Promise<string> => {
    const ext = typeof mimeType === 'string' ? DOC_EXTENSIONS[mimeType.split(';')[0].trim().toLowerCase()] : undefined;
    if (!ext) return 'This kind of file cannot be opened.';
    if (!(data instanceof Uint8Array) || data.byteLength === 0 || data.byteLength > MAX_DOC_BYTES) {
      return 'The file is empty or too large to open.';
    }
    const folder = join(tmpdir(), 'LiteRetail', 'documents');
    await mkdir(folder, { recursive: true });
    const file = join(folder, `document-${randomUUID()}.${ext}`);
    await writeFile(file, data);
    return shell.openPath(file); // '' = opened; otherwise Windows' reason (e.g. no app for PDFs)
  });
}
