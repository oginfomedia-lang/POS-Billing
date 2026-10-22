// Wraps the entire app. Blocks access and shows the activation screen if the shop licence
// (kept on the Main PC's server, shared by every counter) is missing, invalid, expired or
// for a different Main PC.
import { useEffect, useState } from 'react';
import { LicensePage } from '../pages/auth/LicensePage';
import { getLicense, type LicenseStatus } from '../services/api/licenseApi';
import { useAuthStore } from '../store/authStore';
import { useCounterStore } from '../store/counterStore';
import { useOfflineStore } from '../store/offlineStore';

const WARNING_DAYS = 30;
// Offline billing may skip this check (server unreachable) only if the licence was seen valid this recently.
const OFFLINE_GRACE_MS = 7 * 24 * 60 * 60 * 1000;
const LICENCE_OK_KEY = 'lr-licence-ok-at';

function rememberLicenceOk(): void {
  try { localStorage.setItem(LICENCE_OK_KEY, String(Date.now())); } catch { /* private window: no offline grace */ }
}

/** Server unreachable: can this PC bill offline? The cashier is still logged in with an open shift, the
 * offline files exist (Electron), and the licence was valid within OFFLINE_GRACE_MS. */
function canBillOffline(): boolean {
  let okAt = 0;
  try { okAt = Number(localStorage.getItem(LICENCE_OK_KEY) || 0); } catch { return false; }
  const user = useAuthStore.getState().user;
  const shift = useOfflineStore.getState().lastShift;
  return Boolean(window.posBridge?.offline) && Date.now() - okAt < OFFLINE_GRACE_MS
    && user !== null && shift !== null && shift.user_id === user.id;
}

export function LicenseGuard({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<LicenseStatus | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [warningDismissed, setWarningDismissed] = useState(false);
  const [offlineMode, setOfflineMode] = useState(false);
  const apiUrl = useCounterStore((s) => s.config?.apiUrl ?? '');

  async function checkLicense() {
    setUnreachable(false);
    try {
      const found = await getLicense();
      if (found.valid || found.required === false) rememberLicenceOk();
      setStatus(found);
    } catch {
      setStatus(null);
      setUnreachable(true);
    }
  }

  useEffect(() => {
    checkLicense();
  }, []);

  if (unreachable && offlineMode) return <>{children}</>;

  if (unreachable) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#0f172a', color: '#e2e8f0', fontFamily: 'system-ui, sans-serif',
        flexDirection: 'column', gap: 12, padding: 24, textAlign: 'center',
      }}>
        <div style={{ fontSize: '1.2em', fontWeight: 700 }}>Cannot reach the LiteRetail server</div>
        <div style={{ color: '#94a3b8', fontSize: '0.9em', maxWidth: 460 }}>
          Check that the Main PC is switched on and connected to the store network.
          Server address: <code>{apiUrl}</code>
        </div>
        <button type="button" className="btn-primary" onClick={checkLicense}>Try again</button>
        {canBillOffline() && (
          <button
            type="button"
            className="btn-secondary"
            onClick={() => { window.location.hash = '#/pos/offline'; setOfflineMode(true); }}
          >
            Bill offline (cash)
          </button>
        )}
      </div>
    );
  }

  // Loading
  if (!status) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#0f172a', color: '#94a3b8', fontFamily: 'system-ui, sans-serif',
        flexDirection: 'column', gap: 16,
      }}>
        <div style={{
          width: 40, height: 40, border: '3px solid #334155', borderTopColor: '#6366f1',
          borderRadius: '50%', animation: 'spin 0.8s linear infinite',
        }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <span style={{ fontSize: '0.9em' }}>Checking license…</span>
      </div>
    );
  }

  // Invalid / expired / not activated (development servers don't require a licence)
  if (!status.valid && status.required !== false) {
    return (
      <LicensePage
        reason={status.reason ?? undefined}
        expiresAt={status.expires_at ?? undefined}
        machineId={status.machine_id}
        onActivated={checkLicense}
      />
    );
  }

  // Valid — show expiry warning if within WARNING_DAYS
  const daysLeft = status.days_left ?? undefined;
  const showWarning = !warningDismissed &&
    daysLeft !== undefined &&
    daysLeft <= WARNING_DAYS;

  return (
    <>
      {showWarning && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, zIndex: 9999,
          background: '#fef3c7', borderBottom: '1px solid #fcd34d',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '8px 20px', gap: 12, fontSize: '0.87em',
        }}>
          <span style={{ color: '#92400e' }}>
            ⚠ Your license expires in <strong>{daysLeft} day{daysLeft !== 1 ? 's' : ''}</strong>.
            Contact your provider to renew.
          </span>
          <button
            type="button"
            onClick={() => setWarningDismissed(true)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: '#92400e', fontWeight: 700, fontSize: '1.1em', lineHeight: 1,
              flexShrink: 0,
            }}
          >✕</button>
        </div>
      )}
      {children}
    </>
  );
}
