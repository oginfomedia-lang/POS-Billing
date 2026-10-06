import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useShiftStore } from '../../store/shiftStore';
import { getErrorMessage } from '../../services/api/httpClient';

export function CloseShiftPage() {
  const { user, logout } = useAuth();
  const { shift, close, busy } = useShiftStore();
  const navigate = useNavigate();

  const [actualCash, setActualCash] = useState('0');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      await close(parseFloat(actualCash) || 0);
      setDone(true);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  if (done) {
    return (
      <div className="admin-page">
        <div className="admin-header">
          <h2>Shift Closed</h2>
          <div className="admin-actions">
            <button className="btn-secondary" onClick={logout}>Logout</button>
          </div>
        </div>
        <div style={{ maxWidth: 400, margin: '40px auto', textAlign: 'center' }}>
          <p className="loading-text">Shift has been closed successfully.</p>
          <button className="btn-primary" onClick={() => navigate('/', { replace: true })}>
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h2>Close Shift — {user?.full_name ?? user?.username}</h2>
        <div className="admin-actions">
          <button className="btn-secondary" onClick={() => navigate('/pos/billing')}>Back to POS</button>
          <button className="btn-secondary" onClick={logout}>Logout</button>
        </div>
      </div>

      <div style={{ maxWidth: 400, margin: '40px auto' }}>
        {shift && (
          <div className="modal-form" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
              <span>Opening Float</span>
              <strong>₹{Number(shift.opening_float).toFixed(2)}</strong>
            </div>
            {shift.expected_cash !== null && (
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                <span>Expected Cash</span>
                <strong>₹{Number(shift.expected_cash).toFixed(2)}</strong>
              </div>
            )}
          </div>
        )}

        {error && <div className="page-error">{error}</div>}

        <form onSubmit={handleSubmit} className="modal-form">
          <label className="field-label">
            Actual Cash Count (₹)
            <input
              className="field-input"
              type="number"
              min="0"
              step="0.01"
              value={actualCash}
              onChange={(e) => setActualCash(e.target.value)}
            />
          </label>
          <div className="modal-buttons">
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Closing…' : 'Close Shift'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
