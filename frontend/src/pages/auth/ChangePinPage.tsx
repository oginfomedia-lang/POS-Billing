// Change own PIN. Required (nothing else works) after first login or an admin's PIN reset; also usable any time.
import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useNavigate } from 'react-router-dom';
import { IconEye, IconEyeOff, IconLogOut, IconShoppingCart } from '../../components/common/Icons';
import { useAuth } from '../../hooks/useAuth';
import { useAuthStore } from '../../store/authStore';
import { getErrorMessage } from '../../services/api/httpClient';

const PIN_RULE = /^[A-Za-z0-9]{4,12}$/;

export function ChangePinPage() {
  const { t } = useTranslation();
  const { isAuthenticated, user, logout } = useAuth();
  const changePin = useAuthStore((s) => s.changePin);
  const navigate = useNavigate();

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (!isAuthenticated || !user) return <Navigate to="/" replace />;
  const required = Boolean(user.must_change_pin);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    if (!PIN_RULE.test(next)) return setError(t('changePin.rules'));
    if (next !== again) return setError(t('changePin.mismatch'));
    setBusy(true);
    try {
      await changePin(current, next);
      navigate(user!.role === 'cashier' ? '/pos' : '/admin', { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const type = show ? 'text' : 'password';
  return (
    <section className="login-page">
      <div className="login-card">
        <div className="login-brand-header">
          <div className="login-brand-logo">
            <IconShoppingCart size={28} color="#ffffff" />
          </div>
          <h1 className="login-title">{required ? t('changePin.title') : t('changePin.voluntary')}</h1>
          <p className="login-subtitle">{user.full_name || user.username}</p>
        </div>

        {required && <div className="login-error" role="status">{t('changePin.required')}</div>}
        {error && <div className="login-error">{error}</div>}

        <form onSubmit={handleSubmit} className="login-form">
          <label className="field-label">
            <span>{t('changePin.current')}</span>
            <div className="password-field">
              <input
                className="field-input"
                type={type}
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                maxLength={12}
                required
                autoFocus
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShow((v) => !v)}
                aria-label={show ? 'Hide password' : 'Show password'}
                title={show ? 'Hide password' : 'Show password'}
              >
                {show ? <IconEyeOff size={18} /> : <IconEye size={18} />}
              </button>
            </div>
          </label>
          <label className="field-label">
            <span>{t('changePin.new')}</span>
            <input
              className="field-input"
              type={type}
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              minLength={4}
              maxLength={12}
              required
            />
            <span className="hint-text">{t('changePin.rules')}</span>
          </label>
          <label className="field-label">
            <span>{t('changePin.confirm')}</span>
            <input
              className="field-input"
              type={type}
              autoComplete="new-password"
              value={again}
              onChange={(e) => setAgain(e.target.value)}
              minLength={4}
              maxLength={12}
              required
            />
          </label>

          <button className="btn-primary btn-login-submit" type="submit" disabled={busy}>
            <span>{busy ? t('changePin.saving') : t('changePin.save')}</span>
          </button>
          <button type="button" className="btn-secondary" onClick={logout}>
            <IconLogOut size={16} />
            <span>{t('changePin.signOut')}</span>
          </button>
        </form>
      </div>
    </section>
  );
}
