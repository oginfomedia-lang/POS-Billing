// Shop licence activation. One key per shop, issued for the Main PC's machine ID; it can be
// entered on any PC in the store because the server on the Main PC checks and keeps it.
import { useState } from 'react';
import { activateLicense } from '../../services/api/licenseApi';

interface Props {
  reason?: string;
  expiresAt?: string;
  /** The Main PC's machine ID (from the server). */
  machineId: string;
  onActivated: () => void;
}

export function LicensePage({ reason, expiresAt, machineId, onActivated }: Props) {
  const [key, setKey] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [copied, setCopied] = useState(false);

  async function handleActivate() {
    if (!key.trim()) return;
    setStatus('loading');
    setErrorMsg('');
    let reason: string | null;
    try {
      const result = await activateLicense(key.trim());
      if (result.valid) {
        onActivated();
        return;
      }
      reason = result.reason;
    } catch {
      reason = 'unreachable';
    }
    setStatus('error');
    setErrorMsg(
      reason === 'expired' ? 'This license key has expired.' :
      reason === 'wrong_machine' ? "This key was issued for a different Main PC. Use the Main PC's machine ID shown above." :
      reason === 'invalid_key' ? 'Invalid license key. Please check and try again.' :
      reason === 'unreachable' ? 'Cannot reach the LiteRetailer server on the Main PC. Check the network and try again.' :
      'Activation failed. Please contact support.'
    );
  }

  function copyMachineId() {
    navigator.clipboard.writeText(machineId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const isExpired = reason === 'expired';

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
      fontFamily: 'system-ui, sans-serif',
      padding: 24,
    }}>
      <div style={{
        width: '100%', maxWidth: 480, background: '#fff', borderRadius: 20,
        boxShadow: '0 25px 60px rgba(0,0,0,0.4)', overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
          padding: '28px 32px',
          textAlign: 'center',
        }}>
          <div style={{
            width: 64, height: 64, borderRadius: 16, background: 'rgba(255,255,255,0.15)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 14px', fontSize: 28,
          }}>🔐</div>
          <div style={{ color: '#fff', fontWeight: 800, fontSize: '1.3em', marginBottom: 6 }}>
            {isExpired ? 'License Expired' : 'Activate Application'}
          </div>
          <div style={{ color: 'rgba(255,255,255,0.75)', fontSize: '0.88em' }}>
            {isExpired
              ? `Your license expired on ${expiresAt ? new Date(expiresAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}. Please contact your provider to renew.`
              : 'One licence key activates LiteRetailer on every PC in this shop.'}
          </div>
        </div>

        <div style={{ padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* Machine ID */}
          <div>
            <div style={{ fontSize: '0.78em', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>
              Main PC Machine ID
            </div>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '12px 14px', background: '#f8fafc',
              border: '1px solid #e2e8f0', borderRadius: 10,
            }}>
              <code style={{ flex: 1, fontFamily: 'monospace', fontSize: '1em', fontWeight: 700, color: '#1e293b', letterSpacing: '0.5px' }}>
                {machineId || '…'}
              </code>
              <button
                type="button"
                onClick={copyMachineId}
                style={{
                  padding: '6px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
                  background: copied ? '#dcfce7' : '#eff6ff',
                  color: copied ? '#15803d' : '#2563eb',
                  fontWeight: 600, fontSize: '0.82em', flexShrink: 0,
                  transition: 'all 0.15s',
                }}
              >
                {copied ? '✓ Copied' : 'Copy'}
              </button>
            </div>
            <div style={{ fontSize: '0.76em', color: '#94a3b8', marginTop: 6 }}>
              Share this with your provider to get the shop's licence key. It is the same on every PC in the shop.
            </div>
          </div>

          {/* License key input */}
          <div>
            <div style={{ fontSize: '0.78em', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>
              License Key
            </div>
            <textarea
              value={key}
              onChange={(e) => { setKey(e.target.value); setStatus('idle'); setErrorMsg(''); }}
              placeholder="Paste your license key here…"
              rows={3}
              style={{
                width: '100%', padding: '12px 14px', border: `1px solid ${status === 'error' ? '#fca5a5' : '#e2e8f0'}`,
                borderRadius: 10, fontSize: '0.88em', fontFamily: 'monospace',
                background: status === 'error' ? '#fef2f2' : '#fff',
                resize: 'none', outline: 'none', boxSizing: 'border-box',
                color: '#1e293b',
              }}
            />
            {status === 'error' && (
              <div style={{ fontSize: '0.82em', color: '#dc2626', marginTop: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
                <span>⚠</span> {errorMsg}
              </div>
            )}
          </div>

          {/* Activate button */}
          <button
            type="button"
            onClick={handleActivate}
            disabled={!key.trim() || status === 'loading'}
            style={{
              width: '100%', padding: '13px', borderRadius: 10, border: 'none',
              background: !key.trim() || status === 'loading'
                ? '#e2e8f0' : 'linear-gradient(135deg, #4f46e5, #7c3aed)',
              color: !key.trim() || status === 'loading' ? '#94a3b8' : '#fff',
              fontWeight: 700, fontSize: '1em', cursor: !key.trim() || status === 'loading' ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s',
            }}
          >
            {status === 'loading' ? 'Activating…' : isExpired ? 'Renew License' : 'Activate'}
          </button>

          <div style={{ textAlign: 'center', fontSize: '0.78em', color: '#94a3b8' }}>
            Need help? Contact your software provider.
          </div>
        </div>
      </div>
    </div>
  );
}
