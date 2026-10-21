// Bottom bar: counter code and live server status.
import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useServerStatus, type ServerStatus } from '../../hooks/useServerStatus';
import { LanguageSwitcher } from '../common/LanguageSwitcher';
import { UpdateNotice } from './UpdateNotice';
import { useCounterStore } from '../../store/counterStore';
import { useOfflineStore } from '../../store/offlineStore';
import { VENDOR_NAME, VENDOR_PHONE } from '../../utils/brand';

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
  const pending = useOfflineStore((s) => s.pending);

  return (
    <footer className="status-bar">
      <span>{t('status.counter', { code: config?.counterCode ?? '—' })}</span>
      <span className={`status-pill status-${status}`}>{t(STATUS_TEXT[status])}</span>
      {pending > 0 && <span className="status-pill status-database-down">{t('offline.waiting', { count: pending })}</span>}
      <span className="status-muted">{config?.apiUrl}</span>
      <UpdateNotice />
      <LanguageSwitcher className="no-print" />
      <span className="status-vendor">{VENDOR_NAME} · {VENDOR_PHONE}</span>
    </footer>
  );
}
