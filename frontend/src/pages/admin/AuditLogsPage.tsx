// Audit log viewer. Filters combine (all must match) and apply as you type:
//   User:   a role ("admin", "manager", "cashier") or part of a username / full name
//   Action: part of the action ("sale" finds sale.complete, sale.void, ...)
//   Type:   the kind of record (user, sale, product, ...)
// Both text boxes suggest what exists in the log.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getErrorMessage, httpClient } from '../../services/api/httpClient';
import type { AuditFilterValues, AuditLogOut, PagedResponse } from '../../types/api';
import { AdminNav } from '../../components/admin/AdminNav';
import { formatDateTime } from '../../utils/format';

const PER_PAGE = 50;
const TYPE_DELAY_MS = 350;

export function AuditLogsPage() {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<AuditLogOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Filters
  const [filterUser, setFilterUser] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterType, setFilterType] = useState('');
  const [choices, setChoices] = useState<AuditFilterValues | null>(null);
  const requestNo = useRef(0);

  useEffect(() => {
    httpClient.get<AuditFilterValues>('/audit-logs/filters').then((r) => setChoices(r.data)).catch(() => setChoices(null));
  }, []);

  async function fetchLogs(p: number) {
    const mine = ++requestNo.current;
    setLoading(true);
    setError('');
    try {
      const resp = await httpClient.get<PagedResponse<AuditLogOut>>('/audit-logs', {
        params: {
          page: p,
          per_page: PER_PAGE,
          user: filterUser.trim() || undefined,
          action: filterAction.trim() || undefined,
          entity_type: filterType || undefined,
        },
      });
      if (mine !== requestNo.current) return; // an older request answering late
      setLogs(resp.data.items);
      setTotal(resp.data.total);
    } catch (err) {
      if (mine === requestNo.current) setError(getErrorMessage(err));
    } finally {
      if (mine === requestNo.current) setLoading(false);
    }
  }

  // Filters apply as you type (after a short pause), starting again at page 1.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (page !== 1) setPage(1);
      else fetchLogs(1);
    }, TYPE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [filterUser, filterAction, filterType]);

  useEffect(() => { fetchLogs(page); }, [page]);

  const filtered = filterUser.trim() !== '' || filterAction.trim() !== '' || filterType !== '';

  function clearFilters() {
    setFilterUser('');
    setFilterAction('');
    setFilterType('');
  }

  return (
    <div className="admin-page">
      <AdminNav />
      <div className="admin-header">
        <h2>{t('audit.title')}</h2>
      </div>

      <div className="filter-bar">
        <input
          className="field-input filter-input"
          list="audit-user-options"
          placeholder={t('audit.userPlaceholder')}
          aria-label={t('audit.colUser')}
          value={filterUser}
          onChange={(e) => setFilterUser(e.target.value)}
        />
        <datalist id="audit-user-options">
          {choices?.roles.map((r) => (
            <option key={`role-${r}`} value={r}>{t('audit.everyoneWithRole', { role: t(`roles.${r}` as 'roles.admin') })}</option>
          ))}
          {choices?.users.map((u) => (
            <option key={u.username} value={u.username}>{`${u.full_name} · ${t(`roles.${u.role}` as 'roles.admin')}`}</option>
          ))}
        </datalist>

        <input
          className="field-input filter-input"
          list="audit-action-options"
          placeholder={t('audit.actionPlaceholder')}
          aria-label={t('audit.colAction')}
          value={filterAction}
          onChange={(e) => setFilterAction(e.target.value)}
        />
        <datalist id="audit-action-options">
          {choices?.actions.map((a) => <option key={a} value={a} />)}
        </datalist>

        <select
          className="field-input filter-input"
          aria-label={t('audit.colEntity')}
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          <option value="">{t('audit.allTypes')}</option>
          {choices?.entity_types.map((ty) => <option key={ty} value={ty}>{ty}</option>)}
        </select>

        <button className="btn-secondary" onClick={clearFilters} disabled={!filtered}>{t('audit.clear')}</button>
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      <div className="table-card">
        <table className="data-table audit-table">
          <thead>
            <tr>
              <th>{t('audit.colTime')}</th><th>{t('audit.colUser')}</th><th>{t('audit.colAction')}</th><th>{t('audit.colEntity')}</th><th>{t('audit.colId')}</th><th>{t('audit.colIp')}</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id}>
                <td className="ts-cell">{formatDateTime(l.created_at)}</td>
                <td>{l.username ?? '—'}</td>
                <td><code>{l.action}</code></td>
                <td>{l.entity_type}</td>
                <td>{l.entity_id ?? '—'}</td>
                <td>{l.ip_address ?? '—'}</td>
              </tr>
            ))}
            {logs.length === 0 && !loading && (
              <tr><td colSpan={6} className="empty-row">{filtered ? t('audit.emptyFiltered') : t('audit.empty')}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('common.prev')}</button>
        <span>{t('common.pageInfo', { page, total })}</span>
        <button disabled={page * PER_PAGE >= total} onClick={() => setPage(page + 1)}>{t('common.next')}</button>
      </div>
    </div>
  );
}
