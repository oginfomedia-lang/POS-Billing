// Bottom bar: counter code and live server status.
import { useServerStatus, type ServerStatus } from '../../hooks/useServerStatus';
import { useCounterStore } from '../../store/counterStore';

const STATUS_TEXT: Record<ServerStatus, string> = {
  checking: 'Checking server…',
  online: 'Server OK',
  'database-down': 'Server up, database DOWN',
  offline: 'Server OFFLINE',
};

export function StatusBar() {
  const config = useCounterStore((s) => s.config);
  const status = useServerStatus(config !== null);

  return (
    <footer className="status-bar">
      <span>Counter: {config?.counterCode ?? '—'}</span>
      <span className={`status-pill status-${status}`}>{STATUS_TEXT[status]}</span>
      <span className="status-muted">{config?.apiUrl}</span>
    </footer>
  );
}
