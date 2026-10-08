// Bottom bar: counter code and live server status.
import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useServerStatus, type ServerStatus } from '../../hooks/useServerStatus';
import { LanguageSwitcher } from '../common/LanguageSwitcher';
import { useCounterStore } from '../../store/counterStore';

const STATUS_TEXT: Record<ServerStatus, ParseKeys> = {
  checking: 'status.checking',
  online: 'status.online',
  'database-down': 'status.dbDown',
  offline: 'status.offline',
};

export function StatusBar() {
  const { t } = useTranslation();
  const config = useCounterStore((s) => s.config);
  const status = useServerStatus(config !== null);

  return (
    <footer className="status-bar">
      <span>{t('status.counter', { code: config?.counterCode ?? '—' })}</span>
      <span className={`status-pill status-${status}`}>{t(STATUS_TEXT[status])}</span>
      <span className="status-muted">{config?.apiUrl}</span>
      <LanguageSwitcher className="no-print" />
    </footer>
  );
}
