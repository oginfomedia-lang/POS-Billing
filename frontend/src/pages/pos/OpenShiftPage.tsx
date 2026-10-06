// Enter opening cash and open a shift.
import { type FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '../../services/api/httpClient';
import { getActiveShift, openShift } from '../../services/api/shiftApi';
import { useCounterStore } from '../../store/counterStore';
import { toPaise } from '../../utils/money';

export function OpenShiftPage() {
  const navigate = useNavigate();
  const counterCode = useCounterStore((s) => s.config?.counterCode ?? '');

  const [openingCash, setOpeningCash] = useState('0');
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // Already have a shift? Go straight to billing.
  useEffect(() => {
    getActiveShift()
      .then((shift) => {
        if (shift) navigate('/pos/billing', { replace: true });
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setChecking(false));
  }, [navigate]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!Number.isFinite(toPaise(openingCash))) {
      setError('Enter a valid amount.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await openShift(counterCode, openingCash);
      navigate('/pos/billing', { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (checking) return <p className="loading-text">Checking shift…</p>;

  return (
    <section className="login-page">
      <div className="login-card">
        <h1 className="login-title">Open Shift</h1>
        <p className="login-subtitle">Counter {counterCode}</p>

        {error && <div className="login-error">{error}</div>}

        <form onSubmit={handleSubmit} className="login-form">
          <label className="field-label">
            Opening cash in drawer
            <input
              className="field-input"
              inputMode="decimal"
              value={openingCash}
              onChange={(e) => setOpeningCash(e.target.value)}
              onFocus={(e) => e.target.select()}
              required
              autoFocus
            />
          </label>
          <button className="btn-primary" type="submit" disabled={busy}>
            {busy ? 'Opening…' : 'Open Shift'}
          </button>
          <button className="btn-secondary" type="button" onClick={() => navigate('/pos')}>Back</button>
        </form>
      </div>
    </section>
  );
}
