// Cashier / admin login screen.
import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { LanguageSwitcher } from '../../components/common/LanguageSwitcher';
import { IconLogOut, IconShoppingCart } from '../../components/common/Icons';
import { useAuth } from '../../hooks/useAuth';
import { getErrorMessage } from '../../services/api/httpClient';
import { lastStoreName } from '../../store/storeContext';
import { VENDOR_NAME } from '../../utils/brand';

export function LoginPage() {
  const { t } = useTranslation();
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
        <LanguageSwitcher className="login-language" />
        <div className="login-brand-header">
          <div className="login-brand-logo">
            <IconShoppingCart size={28} color="#ffffff" />
          </div>
          <h1 className="login-title">{lastStoreName() || 'SUPERMARKET POS'}</h1>
          <p className="login-subtitle">{t('login.subtitle')}</p>
        </div>

        {error && <div className="login-error">{error}</div>}

        <form onSubmit={handleSubmit} className="login-form">
          <label className="field-label">
            <span>{t('login.username')}</span>
            <input
              className="field-input"
              type="text"
              placeholder={t('login.usernamePlaceholder')}
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </label>

          <label className="field-label">
            <span>{t('login.pin')}</span>
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
            <span>{busy ? t('login.signingIn') : t('login.signIn')}</span>
          </button>
        </form>

        <div className="login-footer-hint">
          <span>🔒 {t('login.secured', { store: lastStoreName() })}</span>
          <div className="vendor-credit">Powered by {VENDOR_NAME}</div>
        </div>
      </div>
    </section>
  );
}

