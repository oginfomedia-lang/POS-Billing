// Backup Management page — admin only.
// Lists all pg_dump backups, lets the admin create, verify, download and delete them.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AdminNav } from '../../components/admin/AdminNav';
import { IconDatabase, IconDownload, IconShield, IconTrash } from '../../components/common/Icons';
import { backupApi } from '../../services/api/backupApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { BackupRunOut } from '../../types/api';
import { formatDateTime } from '../../utils/format';

function formatBytes(bytes: number | null): string {
  if (bytes === null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function StatusBadge({ status }: { status: string }) {
  const cls = {
    running: 'badge-info',
    success: 'badge-success',
    failed: 'badge-danger',
    deleted: 'badge-neutral',
  }[status] ?? 'badge-neutral';
  return <span className={`status-badge ${cls}`}>{status}</span>;
}

export function BackupPage() {
  const { t } = useTranslation();
  const [backups, setBackups] = useState<BackupRunOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  async function load(p = page) {
    setLoading(true);
    setError('');
    try {
      const resp = await backupApi.list(p, 20);
      setBackups(resp.data.items);
      setTotal(resp.data.total);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [page]);

  async function handleCreate() {
    setCreating(true);
    setActionError('');
    try {
      await backupApi.create();
      await load(1);
      setPage(1);
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function handleDownload(b: BackupRunOut) {
    setBusyId(b.id);
    setActionError('');
    try {
      const resp = await backupApi.downloadBlob(b.id);
      const url = URL.createObjectURL(resp.data as Blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = b.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      // Refresh to update download_count
      await load(page);
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleVerify(b: BackupRunOut) {
    setBusyId(b.id);
    setActionError('');
    try {
      await backupApi.verify(b.id);
      await load(page);
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(id: number) {
    setDeleteConfirmId(null);
    setBusyId(id);
    setActionError('');
    try {
      await backupApi.delete(id);
      await load(page);
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  const perPage = 20;

  return (
    <div className="admin-page">
      <AdminNav />

      <div className="admin-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <IconDatabase size={22} />
          <h2>{t('backup.title')}</h2>
        </div>
        <button
          className="btn-primary"
          onClick={handleCreate}
          disabled={creating}
        >
          {creating ? t('backup.creating') : t('backup.createBtn')}
        </button>
      </div>

      {creating && (
        <div className="page-info">{t('backup.creatingHint')}</div>
      )}

      {actionError && <div className="page-error">{actionError}</div>}
      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      {/* Delete confirmation */}
      {deleteConfirmId !== null && (
        <div className="confirm-overlay">
          <div className="confirm-card">
            <p>{t('backup.deleteConfirm')}</p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn-secondary" onClick={() => setDeleteConfirmId(null)}>
                {t('common.cancel')}
              </button>
              <button className="btn-danger" onClick={() => handleDelete(deleteConfirmId)}>
                {t('backup.deleteBtn')}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="table-card">
        <table className="data-table backup-table">
          <thead>
            <tr>
              <th>{t('backup.colStarted')}</th>
              <th>{t('backup.colFilename')}</th>
              <th>{t('backup.colSize')}</th>
              <th>{t('backup.colStatus')}</th>
              <th>{t('backup.colStorage')}</th>
              <th>{t('backup.colVerified')}</th>
              <th>{t('backup.colDownloads')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {backups.map((b) => (
              <tr key={b.id}>
                <td className="ts-cell">{b.started_at ? formatDateTime(b.started_at) : '—'}</td>
                <td>
                  <span style={{ fontFamily: 'monospace', fontSize: '0.85em' }}>{b.filename}</span>
                  {b.checksum_sha256 && (
                    <div style={{ fontSize: '0.75em', color: 'var(--color-text-muted)', marginTop: 2 }}>
                      SHA-256: {b.checksum_sha256.slice(0, 16)}…
                    </div>
                  )}
                  {b.error_message && (
                    <div style={{ fontSize: '0.75em', color: 'var(--color-danger)', marginTop: 2 }}>
                      {b.error_message}
                    </div>
                  )}
                </td>
                <td>{formatBytes(b.file_size_bytes)}</td>
                <td><StatusBadge status={b.status} /></td>
                <td>
                  <span className={`badge-neutral ${b.storage_location === 's3' ? 'badge-info' : ''}`}>
                    {b.storage_location}
                  </span>
                </td>
                <td>
                  {b.verified ? (
                    <span style={{ color: 'var(--color-success)' }}>
                      ✓ {b.verified_at ? formatDateTime(b.verified_at ?? '') : ''}
                    </span>
                  ) : (
                    <span style={{ color: 'var(--color-text-muted)' }}>—</span>
                  )}
                </td>
                <td>{b.download_count}</td>
                <td>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {b.status === 'success' && (
                      <>
                        <button
                          className="btn-icon"
                          title={t('backup.downloadBtn')}
                          disabled={busyId === b.id}
                          onClick={() => handleDownload(b)}
                        >
                          <IconDownload size={16} />
                        </button>
                        {!b.verified && (
                          <button
                            className="btn-icon"
                            title={t('backup.verifyBtn')}
                            disabled={busyId === b.id}
                            onClick={() => handleVerify(b)}
                          >
                            <IconShield size={16} />
                          </button>
                        )}
                      </>
                    )}
                    {b.status !== 'deleted' && (
                      <button
                        className="btn-icon btn-icon-danger"
                        title={t('backup.deleteBtn')}
                        disabled={busyId === b.id}
                        onClick={() => setDeleteConfirmId(b.id)}
                      >
                        <IconTrash size={16} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {backups.length === 0 && !loading && (
              <tr>
                <td colSpan={8} className="empty-row">{t('backup.empty')}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('common.prev')}</button>
        <span>{t('common.pageInfo', { page, total })}</span>
        <button disabled={backups.length < perPage} onClick={() => setPage(page + 1)}>{t('common.next')}</button>
      </div>
    </div>
  );
}
