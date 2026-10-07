// Audit log viewer.
import { useEffect, useState } from 'react';
import { getErrorMessage, httpClient } from '../../services/api/httpClient';
import type { AuditLogOut, PagedResponse } from '../../types/api';
import { AdminNav } from '../../components/admin/AdminNav';

export function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLogOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Filters
  const [filterEntity, setFilterEntity] = useState('');
  const [filterAction, setFilterAction] = useState('');

  async function fetchLogs(p = page) {
    setLoading(true);
    setError('');
    try {
      const resp = await httpClient.get<PagedResponse<AuditLogOut>>('/audit-logs', {
        params: {
          page: p,
          per_page: 50,
          entity_type: filterEntity || undefined,
          action: filterAction || undefined,
        },
      });
      setLogs(resp.data.items);
      setTotal(resp.data.total);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchLogs(); }, [page]);

  function applyFilters() {
    setPage(1);
    fetchLogs(1);
  }

  function fmt(ts: string) {
    return new Date(ts).toLocaleString();
  }

  return (
    <div className="admin-page">
      <AdminNav />
      <div className="admin-header">
        <h2>Audit Logs</h2>
      </div>

      <div className="filter-bar">
        <input
          className="field-input filter-input"
          placeholder="Entity type (e.g. user)"
          value={filterEntity}
          onChange={e => setFilterEntity(e.target.value)}
        />
        <input
          className="field-input filter-input"
          placeholder="Action (e.g. user.create)"
          value={filterAction}
          onChange={e => setFilterAction(e.target.value)}
        />
        <button className="btn-secondary" onClick={applyFilters}>Filter</button>
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">Loading…</div>}

      <div className="table-card">
        <table className="data-table audit-table">
          <thead>
            <tr>
              <th>Time</th><th>User</th><th>Action</th><th>Entity</th><th>ID</th><th>IP</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id}>
                <td className="ts-cell">{fmt(l.created_at)}</td>
                <td>{l.username ?? '—'}</td>
                <td><code>{l.action}</code></td>
                <td>{l.entity_type}</td>
                <td>{l.entity_id ?? '—'}</td>
                <td>{l.ip_address ?? '—'}</td>
              </tr>
            ))}
            {logs.length === 0 && !loading && (
              <tr><td colSpan={6} className="empty-row">No log entries found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
        <span>Page {page} · {total} entries</span>
        <button disabled={logs.length < 50} onClick={() => setPage(page + 1)}>Next →</button>
      </div>
    </div>
  );
}
