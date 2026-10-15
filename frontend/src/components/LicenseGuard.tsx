// Wraps the entire app. Blocks access and shows the activation screen if the
// license is missing, invalid, expired, or for the wrong machine.
import { useEffect, useState } from 'react';
import { LicensePage } from '../pages/auth/LicensePage';

interface LicenseStatus {
  valid: boolean;
  reason?: string;
  expiresAt?: string;
  daysLeft?: number;
  customerName?: string;
}

const WARNING_DAYS = 30;

export function LicenseGuard({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<LicenseStatus | null>(null);
  const [warningDismissed, setWarningDismissed] = useState(false);

  async function checkLicense() {
    // Skip in non-Electron environments (browser dev mode)
    if (!window.posBridge?.checkLicense) {
      setStatus({ valid: true });
      return;
    }
    const result = await window.posBridge.checkLicense();
    setStatus(result);
  }

  useEffect(() => {
    checkLicense();
  }, []);

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

  // Invalid / expired / not activated
  if (!status.valid) {
    return (
      <LicensePage
        reason={status.reason}
        expiresAt={status.expiresAt}
        onActivated={checkLicense}
      />
    );
  }

  // Valid — show expiry warning if within WARNING_DAYS
  const showWarning = !warningDismissed &&
    status.daysLeft !== undefined &&
    status.daysLeft <= WARNING_DAYS;

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
            ⚠ Your license expires in <strong>{status.daysLeft} day{status.daysLeft !== 1 ? 's' : ''}</strong>.
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
