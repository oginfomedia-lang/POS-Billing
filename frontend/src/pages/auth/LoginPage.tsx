// Cashier / admin login screen.
import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { LanguageSwitcher } from '../../components/common/LanguageSwitcher';
import { IconEye, IconEyeOff, IconLogOut, IconShoppingCart } from '../../components/common/Icons';
import { useAuth } from '../../hooks/useAuth';
import { useAuthStore } from '../../store/authStore';
import { getErrorMessage } from '../../services/api/httpClient';
import { lastStoreName } from '../../store/storeContext';
import { VENDOR_NAME } from '../../utils/brand';

export function LoginPage() {
  const { t } = useTranslation();
  const { login, isAuthenticated, user } = useAuth();
  const endedReason = useAuthStore((s) => s.endedReason);
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [pin, setPin] = useState('');
  const [showPin, setShowPin] = useState(false);
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
          <h1 className="login-title">{lastStoreName() || 'LiteRetail'}</h1>
          <p className="login-subtitle">{t('login.subtitle')}</p>
        </div>

        {error && <div className="login-error">{error}</div>}
        {!error && endedReason && <div className="login-error" role="status">{endedReason}</div>}

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
            <div className="password-field">
              <input
                className="field-input"
                type={showPin ? 'text' : 'password'}
                placeholder="••••••••"
                autoComplete="current-password"
                value={pin}
                onChange={(e) => setPin(e.target.value)}
                minLength={4}
                maxLength={12}
                required
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPin((v) => !v)}
                aria-label={showPin ? 'Hide password' : 'Show password'}
                title={showPin ? 'Hide password' : 'Show password'}
              >
                {showPin ? <IconEyeOff size={18} /> : <IconEye size={18} />}
              </button>
            </div>
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

