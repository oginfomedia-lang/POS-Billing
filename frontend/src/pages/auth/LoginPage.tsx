// Cashier / admin login screen.
import { type FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { IconLogOut, IconShoppingCart } from '../../components/common/Icons';
import { useAuth } from '../../hooks/useAuth';
import { getErrorMessage } from '../../services/api/httpClient';

export function LoginPage() {
  const { login, isAuthenticated, user } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // Redirect when already authenticated (or just after a successful login).
  useEffect(() => {
    if (isAuthenticated && user) {
      const dest =
        user.role === 'admin' || user.role === 'manager' ? '/admin' : '/pos';
      navigate(dest, { replace: true });
    }
  }, [isAuthenticated, user, navigate]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await login(username.trim(), pin);
      // Navigation is handled by the useEffect above once store updates.
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="login-page">
      <div className="login-card">
        <div className="login-brand-header">
          <div className="login-brand-logo">
            <IconShoppingCart size={28} color="#ffffff" />
          </div>
          <h1 className="login-title">SUPERMARKET POS</h1>
          <p className="login-subtitle">Billing & Inventory Terminal Login</p>
        </div>

        {error && <div className="login-error">{error}</div>}

        <form onSubmit={handleSubmit} className="login-form">
          <label className="field-label">
            <span>Staff Username</span>
            <input
              className="field-input"
              type="text"
              placeholder="e.g. admin or cashier1"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </label>

          <label className="field-label">
            <span>Passcode / PIN</span>
            <input
              className="field-input"
              type="password"
              inputMode="numeric"
              placeholder="••••••••"
              autoComplete="current-password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              minLength={4}
              maxLength={8}
              required
            />
          </label>

          <button className="btn-primary btn-login-submit" type="submit" disabled={busy}>
            <IconLogOut size={18} />
            <span>{busy ? 'Authenticating Terminal…' : 'Sign In to POS'}</span>
          </button>
        </form>

        <div className="login-footer-hint">
          <span>🔒 Secured Supermarket Counter Session</span>
        </div>
      </div>
    </section>
  );
}

