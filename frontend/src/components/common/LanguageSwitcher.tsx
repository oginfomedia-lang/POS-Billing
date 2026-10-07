// English / मराठी picker. Changing it re-renders every screen immediately and is remembered on this till.
import { useTranslation } from 'react-i18next';
import { LANGUAGES } from '../../i18n';

export function LanguageSwitcher({ className = '' }: { className?: string }) {
  const { t, i18n } = useTranslation();
  return (
    <select
      className={`language-switcher ${className}`}
      value={i18n.resolvedLanguage}
      onChange={(e) => i18n.changeLanguage(e.target.value)}
      aria-label={t('app.language')}
      title={t('app.language')}
    >
      {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
    </select>
  );
}
