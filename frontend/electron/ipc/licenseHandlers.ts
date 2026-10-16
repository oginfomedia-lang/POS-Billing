// License validation IPC handlers.
// Validates the stored key offline: HMAC signature → machine ID → expiry date.
import { ipcMain } from 'electron';
import { createHmac, createHash } from 'node:crypto';
import * as os from 'node:os';
import { IPC } from './channels';
import { readLicenseKey, writeLicenseKey } from '../config/licenseConfig';

// HMAC secret — must match the value on your license-admin server.
// Change this before distributing to customers; once changed, old keys stop working.
const SECRET = '69c2713fd5fb902bd0d22a33b7ccc958a22ab921f0ee66a50d1ca045fcf5ab54';

interface LicensePayload {
  product: string;
  customer: string;
  mid: string;
  iat: string;
  exp: string;
}

type ValidateResult =
  | { valid: true; payload: LicensePayload; daysLeft: number }
  | { valid: false; reason: string; expiresAt?: string };

// Stable 16-char fingerprint for this machine.
function getMachineId(): string {
  return createHash('sha256')
    .update(os.hostname() + os.platform() + os.arch())
    .digest('hex')
    .slice(0, 16);
}

// base64url → UTF-8 string (handles missing padding).
function b64urlDecode(s: string): string {
  const padded = s + '='.repeat((4 - (s.length % 4)) % 4);
  return Buffer.from(padded.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf-8');
}

function validateKey(key: string): ValidateResult {
  if (!key) return { valid: false, reason: 'not_activated' };

  const dotIndex = key.lastIndexOf('.');
  if (dotIndex === -1) return { valid: false, reason: 'invalid_key' };

  const payloadB64 = key.slice(0, dotIndex);
  const sig = key.slice(dotIndex + 1);

  // 1. Verify HMAC signature (first 32 hex chars of SHA-256 HMAC)
  const expectedSig = createHmac('sha256', SECRET)
    .update(payloadB64)
    .digest('hex')
    .slice(0, 32);

  if (sig !== expectedSig) return { valid: false, reason: 'invalid_key' };

  // 2. Decode payload
  let payload: LicensePayload;
  try {
    payload = JSON.parse(b64urlDecode(payloadB64)) as LicensePayload;
  } catch {
    return { valid: false, reason: 'invalid_key' };
  }

  // 3. Check machine ID
  if (payload.mid !== getMachineId()) return { valid: false, reason: 'wrong_machine' };

  // 4. Check expiry
  const expDate = new Date(payload.exp);
  if (Number.isNaN(expDate.getTime())) return { valid: false, reason: 'invalid_key' };

  if (expDate < new Date()) {
    return { valid: false, reason: 'expired', expiresAt: payload.exp };
  }

  const daysLeft = Math.ceil((expDate.getTime() - Date.now()) / 86_400_000);
  return { valid: true, payload, daysLeft };
}

export function registerLicenseHandlers(): void {
  ipcMain.handle(IPC.getMachineId, () => getMachineId());

  ipcMain.handle(IPC.checkLicense, () => {
    const key = readLicenseKey();
    if (!key) return { valid: false, reason: 'not_activated' };
    const result = validateKey(key);
    if (!result.valid) return result;
    return {
      valid: true,
      expiresAt: result.payload.exp,
      daysLeft: result.daysLeft,
      customerName: result.payload.customer,
    };
  });

  ipcMain.handle(IPC.activateLicense, (_event, key: unknown) => {
    if (typeof key !== 'string') return { ok: false, error: 'invalid_key' };
    const result = validateKey(key.trim());
    if (!result.valid) return { ok: false, error: result.reason };
    writeLicenseKey(key.trim());
    return {
      ok: true,
      expiresAt: result.payload.exp,
      customerName: result.payload.customer,
      daysLeft: result.daysLeft,
    };
  });
}
