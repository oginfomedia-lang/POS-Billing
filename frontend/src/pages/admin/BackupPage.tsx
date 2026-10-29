// Backup Management page — admin only. 5 tabs: Backups · Cloud Uploads · Restore · Replication · Schedule
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AdminNav } from '../../components/admin/AdminNav';
import { IconDatabase, IconDownload, IconShield, IconTrash, IconX } from '../../components/common/Icons';
import { backupApi } from '../../services/api/backupApi';
import { getBlobErrorMessage, getErrorMessage } from '../../services/api/httpClient';
import type {
  BackupRunOut,
  CloudUploadAttemptOut,
  ReplicationStatusOut,
  RestoreRecordOut,
  RestoreStatusOut,
} from '../../types/api';
import { formatDateTime } from '../../utils/format';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatBytes(bytes: number | null): string {
  if (bytes === null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function Pill({ label, ok }: { label: string; ok?: boolean }) {
  const bg = ok === undefined
    ? 'var(--surface-3)'
    : ok ? 'var(--ok-bg)' : 'var(--danger-bg)';
  const color = ok === undefined
    ? 'var(--muted)'
    : ok ? 'var(--ok-text)' : 'var(--danger-text)';
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 999,
      fontSize: 11.5, fontWeight: 700, background: bg, color,
    }}>
      {label}
    </span>
  );
}

// ── Confirm modal ─────────────────────────────────────────────────────────────

function ConfirmModal({
  message, confirmLabel, danger, loading, onConfirm, onClose,
}: {
  message: string; confirmLabel: string; danger?: boolean;
  loading: boolean; onConfirm: () => void; onClose: () => void;
}) {
  return (
    <div className="modal-overlay">
      <div className="modal-box" style={{ maxWidth: 400 }}>
        <div className="modal-header">
          <h3 className="modal-title" style={{ margin: 0 }}>Confirm</h3>
          <button className="modal-close-btn" onClick={onClose}><IconX size={16} /></button>
        </div>
        <div className="modal-form">
          <p style={{ margin: 0, color: 'var(--text-2)', lineHeight: 1.6 }}>{message}</p>
        </div>
        <div className="modal-buttons">
          <button className="btn-secondary" onClick={onClose} disabled={loading}>Cancel</button>
          <button
            className={danger ? 'btn-primary btn-warning-bg' : 'btn-primary'}
            onClick={onConfirm} disabled={loading}
          >
            {loading ? 'Please wait…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Tab: Backups ──────────────────────────────────────────────────────────────

function BackupsTab() {
  const { t } = useTranslation();
  const [backups, setBackups] = useState<BackupRunOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [uploadingId, setUploadingId] = useState<number | null>(null);
  const [fetchingId, setFetchingId] = useState<number | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const perPage = 20;

  async function load(p = page) {
    setLoading(true); setError('');
    try {
      const r = await backupApi.list(p, perPage);
      setBackups(r.data.items); setTotal(r.data.total);
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, [page]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleCreate() {
    setCreating(true); setActionError('');
    try { await backupApi.create(); await load(1); setPage(1); }
    catch (e) { setActionError(getErrorMessage(e)); }
    finally { setCreating(false); }
  }

  async function handleDownload(b: BackupRunOut) {
    setBusyId(b.id); setActionError('');
    try {
      const resp = await backupApi.downloadBlob(b.id);
      const url = URL.createObjectURL(resp.data as Blob);
      const a = document.createElement('a');
      a.href = url; a.download = b.filename;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
      await load(page);
    } catch (e) { setActionError(await getBlobErrorMessage(e)); }
    finally { setBusyId(null); }
  }

  async function handleVerify(b: BackupRunOut) {
    setBusyId(b.id); setActionError('');
    try { await backupApi.verify(b.id); await load(page); }
    catch (e) { setActionError(getErrorMessage(e)); }
    finally { setBusyId(null); }
  }

  async function handleUploadCloud(b: BackupRunOut) {
    setUploadingId(b.id); setActionError('');
    try { await backupApi.uploadToCloud(b.id, 'sftp'); await load(page); }
    catch (e) { setActionError(getErrorMessage(e)); }
    finally { setUploadingId(null); }
  }

  async function handleFetchFromVps(b: BackupRunOut) {
    setFetchingId(b.id); setActionError('');
    try { await backupApi.fetchFromVps(b.id); await load(page); }
    catch (e) { setActionError(getErrorMessage(e)); }
    finally { setFetchingId(null); }
  }

  async function handleDelete(id: number) {
    setDeleteConfirmId(null); setBusyId(id); setActionError('');
    try { await backupApi.delete(id); await load(page); }
    catch (e) { setActionError(getErrorMessage(e)); }
    finally { setBusyId(null); }
  }

  const pages = Math.ceil(total / perPage);

  return (
    <>
      <div className="admin-header" style={{ marginBottom: 16 }}>
        <span style={{ color: 'var(--muted)', fontSize: 13 }}>{total} backup{total !== 1 ? 's' : ''} total</span>
        <button className="btn-primary" onClick={handleCreate} disabled={creating}>
          {creating ? t('backup.creating') : t('backup.createBtn')}
        </button>
      </div>

      {creating && <div className="page-info">{t('backup.creatingHint')}</div>}
      {actionError && <div className="page-error">{actionError}</div>}
      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      {deleteConfirmId !== null && (
        <ConfirmModal
          message={t('backup.deleteConfirm')}
          confirmLabel={t('backup.deleteBtn')}
          danger
          loading={busyId === deleteConfirmId}
          onConfirm={() => handleDelete(deleteConfirmId)}
          onClose={() => setDeleteConfirmId(null)}
        />
      )}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>{t('backup.colStarted')}</th>
              <th>{t('backup.colFilename')}</th>
              <th>{t('backup.colSize')}</th>
              <th>{t('backup.colStatus')}</th>
              <th>{t('backup.colStorage')}</th>
              <th>{t('backup.colVerified')}</th>
              <th className="num">{t('backup.colDownloads')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {backups.map((b) => (
              <tr key={b.id}>
                <td style={{ color: 'var(--muted)', fontWeight: 600 }}>{b.id}</td>
                <td className="ts-cell">{b.started_at ? formatDateTime(b.started_at) : '—'}</td>
                <td>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{b.filename}</span>
                  {b.checksum_sha256 && (
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
                      SHA-256: {b.checksum_sha256.slice(0, 16)}…
                    </div>
                  )}
                  {b.error_message && (
                    <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 2 }}>{b.error_message}</div>
                  )}
                </td>
                <td>{formatBytes(b.file_size_bytes)}</td>
                <td><Pill label={b.status} ok={b.status === 'success' ? true : b.status === 'failed' ? false : undefined} /></td>
                <td><Pill label={b.storage_location} ok={b.storage_location === 's3' || b.storage_location === 'sftp' ? true : undefined} /></td>
                <td>
                  {b.verified
                    ? <span style={{ color: 'var(--ok)', fontWeight: 700 }}>✓ {b.verified_at ? formatDateTime(b.verified_at) : ''}</span>
                    : <span style={{ color: 'var(--muted)' }}>—</span>}
                </td>
                <td className="num">{b.download_count}</td>
                <td>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {b.status === 'success' && (
                      <>
                        <button className="btn-sm" title={t('backup.downloadBtn')} disabled={busyId === b.id} onClick={() => handleDownload(b)}>
                          <IconDownload size={14} />
                        </button>
                        {!b.verified && (
                          <button className="btn-sm" title={t('backup.verifyBtn')} disabled={busyId === b.id} onClick={() => handleVerify(b)}>
                            <IconShield size={14} />
                          </button>
                        )}
                        {b.storage_location === 'local' && (
                          <button
                            className="btn-sm"
                            style={{ fontSize: 11 }}
                            title="Upload to VPS"
                            disabled={uploadingId === b.id}
                            onClick={() => handleUploadCloud(b)}
                          >
                            {uploadingId === b.id ? '…' : '☁ VPS'}
                          </button>
                        )}
                        {b.storage_location === 'sftp' && (
                          <button
                            className="btn-sm"
                            style={{ fontSize: 11 }}
                            title="Fetch backup file from VPS to local machine (needed before restore)"
                            disabled={fetchingId === b.id}
                            onClick={() => handleFetchFromVps(b)}
                          >
                            {fetchingId === b.id ? '…' : '⬇ Fetch'}
                          </button>
                        )}
                      </>
                    )}
                    {b.status !== 'deleted' && (
                      <button
                        className="btn-sm"
                        style={{ color: 'var(--danger)', borderColor: 'var(--danger-border)' }}
                        title={t('backup.deleteBtn')}
                        disabled={busyId === b.id}
                        onClick={() => setDeleteConfirmId(b.id)}
                      >
                        <IconTrash size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {backups.length === 0 && !loading && (
              <tr><td colSpan={8} className="empty-row">{t('backup.empty')}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('common.prev')}</button>
          <span>{t('common.pageInfo', { page, total })}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)}>{t('common.next')}</button>
        </div>
      )}
    </>
  );
}

// ── Tab: Cloud Uploads ────────────────────────────────────────────────────────

function CloudUploadsTab() {
  const { t } = useTranslation();
  const [backupId, setBackupId] = useState('');
  const [uploads, setUploads] = useState<CloudUploadAttemptOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    const id = parseInt(backupId);
    if (!id) return;
    setLoading(true); setError('');
    try {
      const r = await backupApi.listUploads(id);
      setUploads(r.data);
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setLoading(false); }
  }

  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', marginBottom: 16 }}>
        <label className="field-label" style={{ flex: '0 0 200px' }}>
          Backup ID
          <input
            className="field-input"
            type="number"
            placeholder="e.g. 5"
            value={backupId}
            onChange={(e) => setBackupId(e.target.value)}
          />
        </label>
        <button className="btn-primary" onClick={load} disabled={loading || !backupId}>
          {loading ? t('common.loading') : 'Load Uploads'}
        </button>
      </div>

      {error && <div className="page-error">{error}</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Provider</th>
              <th>Bucket</th>
              <th>Key</th>
              <th>Status</th>
              <th className="num">Bytes</th>
              <th>Started</th>
              <th>Completed</th>
            </tr>
          </thead>
          <tbody>
            {uploads.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td><Pill label={u.provider} /></td>
                <td style={{ fontSize: 12, color: 'var(--muted)' }}>{u.bucket ?? '—'}</td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{u.key ?? '—'}</td>
                <td><Pill label={u.status} ok={u.status === 'success' ? true : u.status === 'failed' ? false : undefined} /></td>
                <td className="num">{formatBytes(u.bytes_uploaded)}</td>
                <td className="ts-cell">{u.started_at ? formatDateTime(u.started_at) : '—'}</td>
                <td className="ts-cell">{u.completed_at ? formatDateTime(u.completed_at) : '—'}</td>
              </tr>
            ))}
            {uploads.length === 0 && !loading && (
              <tr><td colSpan={8} className="empty-row">No uploads found. Enter a Backup ID above.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Tab: Restore ──────────────────────────────────────────────────────────────

const RESTORE_PHASE: Record<string, string> = {
  safety_copy: 'Step 1 of 3: saving a safety copy of the current data…',
  restoring: 'Step 2 of 3: loading the backup…',
  updating: 'Step 3 of 3: updating the database to this version…',
};

function RestoreTab() {
  const { t } = useTranslation();
  const [backupId, setBackupId] = useState('');
  const [targetDb, setTargetDb] = useState('');
  const [currentDb, setCurrentDb] = useState('');
  const [restores, setRestores] = useState<RestoreRecordOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // The restore runs on the server: leaving this tab (or the page) does not stop it, it is picked up again here.
  const [active, setActive] = useState<RestoreStatusOut['active']>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);
  const watched = useRef<number | null>(null);
  const perPage = 20;

  async function loadRestores(p = page) {
    setLoading(true); setError('');
    try {
      const r = await backupApi.listRestores(p, perPage);
      setRestores(r.data.items); setTotal(r.data.total);
      setCurrentDb(r.data.current_db);
      setTargetDb((t) => t || r.data.current_db);
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setLoading(false); }
  }

  /** Reads the server's restore status; true while one is running. */
  async function checkStatus(): Promise<boolean> {
    try {
      const { data } = await backupApi.restoreStatus();
      setActive(data.active);
      if (data.active) { watched.current = data.active.id; return true; }
      if (watched.current !== null && data.last) {
        watched.current = null;
        setNotice(data.last.status === 'success'
          ? data.last.live
            ? 'Restore finished. The shop now has the data from the backup: everyone, on every counter, should sign in again.'
            : `Restore into "${data.last.target_db}" finished.`
          : 'Restore failed: see the error in the list below.');
        loadRestores(1); setPage(1);
      }
    } catch { /* server restarting: try again on the next tick */ }
    return false;
  }

  useEffect(() => {
    checkStatus().then((running) => { if (!running) loadRestores(); });
  }, [page]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!active) return;
    const timer = setInterval(checkStatus, 2000);
    return () => clearInterval(timer);
  }, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRestore() {
    setConfirm(false); setSubmitting(true); setError(''); setNotice('');
    try {
      await backupApi.triggerRestore(parseInt(backupId), targetDb);
      setBackupId(''); setTargetDb(currentDb);
      await checkStatus();
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setSubmitting(false); }
  }

  const pages = Math.ceil(total / perPage);

  return (
    <>
      <fieldset className="form-section" style={{ marginBottom: 20 }}>
        <legend>Trigger Restore</legend>
        <div className="form-row">
          <label className="field-label">
            Backup ID *
            <input className="field-input" type="number" placeholder="e.g. 5" value={backupId} onChange={(e) => setBackupId(e.target.value)} />
          </label>
          <label className="field-label">
            Target Database *
            <input className="field-input" placeholder={currentDb} value={targetDb} onChange={(e) => setTargetDb(e.target.value)} />
          </label>
        </div>
        {currentDb && (
          <p className="hint-text">
            This shop's database is <strong>{currentDb}</strong>. Restoring it replaces all current data with the
            backup (a safety copy is taken first).
          </p>
        )}
        <div style={{ marginTop: 12 }}>
          <button
            className="btn-primary btn-warning-bg"
            disabled={submitting || active !== null || !backupId || !targetDb}
            onClick={() => setConfirm(true)}
          >
            {submitting || active ? 'Restoring…' : 'Restore Backup'}
          </button>
        </div>
        {active && (
          <div className="hint-text" style={{ marginTop: 12 }}>
            <strong>Restore #{active.id} into {active.target_db} is running.</strong>{' '}
            {RESTORE_PHASE[active.phase] ?? ''} You can leave this screen: it keeps going on the server.
            {active.live && ' Billing on the counters pauses until it finishes (usually under a minute).'}
          </div>
        )}
      </fieldset>

      {notice && <div className="hint-text" style={{ marginBottom: 12 }}><strong>{notice}</strong></div>}

      {confirm && (
        <ConfirmModal
          message={`This will overwrite database "${targetDb}" with backup #${backupId}. A safety dump will be taken first.${
            targetDb === currentDb ? ' All bills and changes made after this backup will be lost.' : ''
          } Continue?`}
          confirmLabel="Yes, Restore"
          danger
          loading={submitting}
          onConfirm={handleRestore}
          onClose={() => setConfirm(false)}
        />
      )}

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Backup ID</th>
              <th>Target DB</th>
              <th>Status</th>
              <th>Started</th>
              <th>Completed</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {restores.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.backup_run_id ?? '—'}</td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{r.target_db}</td>
                <td><Pill label={r.status} ok={r.status === 'success' ? true : r.status === 'failed' ? false : undefined} /></td>
                <td className="ts-cell">{r.started_at ? formatDateTime(r.started_at) : '—'}</td>
                <td className="ts-cell">{r.completed_at ? formatDateTime(r.completed_at) : '—'}</td>
                <td style={{ fontSize: 11, color: 'var(--danger)', maxWidth: 200, wordBreak: 'break-word' }}>
                  {r.error_message ?? ''}
                </td>
              </tr>
            ))}
            {restores.length === 0 && !loading && (
              <tr><td colSpan={7} className="empty-row">No restore records found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('common.prev')}</button>
          <span>{t('common.pageInfo', { page, total })}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)}>{t('common.next')}</button>
        </div>
      )}
    </>
  );
}

// ── Tab: Replication ──────────────────────────────────────────────────────────

function ReplicationTab() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<ReplicationStatusOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [snapshotting, setSnapshotting] = useState(false);
  const [error, setError] = useState('');

  async function loadStatus() {
    setLoading(true); setError('');
    try {
      const r = await backupApi.getReplication();
      setStatus(r.data);
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setLoading(false); }
  }

  async function takeSnapshot() {
    setSnapshotting(true);
    try { await backupApi.takeReplicationSnapshot(); }
    catch (e) { setError(getErrorMessage(e)); }
    finally { setSnapshotting(false); }
  }

  useEffect(() => { loadStatus(); }, []);

  return (
    <>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
        <button className="btn-secondary" onClick={loadStatus} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh Status'}
        </button>
        <button className="btn-primary" onClick={takeSnapshot} disabled={snapshotting}>
          {snapshotting ? 'Saving…' : 'Save Snapshot'}
        </button>
      </div>

      {error && <div className="page-error">{error}</div>}

      {status && (
        <div
          style={{
            padding: '16px 20px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border)',
            background: 'var(--surface-2)',
            marginBottom: 20,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <span style={{ fontWeight: 700, fontSize: 15 }}>Replication Health</span>
            <Pill
              label={status.is_healthy ? 'Healthy' : status.replica_count === 0 ? 'No Replicas' : 'Degraded'}
              ok={status.replica_count === 0 ? undefined : status.is_healthy}
            />
          </div>

          {status.error && (
            <div className="page-error" style={{ marginBottom: 10 }}>{status.error}</div>
          )}

          {status.replicas.length === 0 ? (
            <p style={{ color: 'var(--muted)', margin: 0, fontSize: 13 }}>
              No standby replicas connected. This is normal if replication is not configured.
            </p>
          ) : (
            <div className="table-card">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Standby Address</th>
                    <th>State</th>
                    <th>Sent LSN</th>
                    <th>Replay LSN</th>
                    <th className="num">Lag (bytes)</th>
                    <th className="num">Lag (sec)</th>
                  </tr>
                </thead>
                <tbody>
                  {status.replicas.map((rep, i) => (
                    <tr key={i}>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{rep.client_addr ?? '—'}</td>
                      <td><Pill label={rep.state} ok={rep.state === 'streaming'} /></td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{rep.sent_lsn}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{rep.replay_lsn}</td>
                      <td className="num">{rep.lag_bytes !== null ? rep.lag_bytes.toLocaleString() : '—'}</td>
                      <td className="num">{rep.lag_seconds !== null ? rep.lag_seconds.toFixed(1) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {!status && !loading && (
        <p style={{ color: 'var(--muted)', fontSize: 13 }}>{t('common.loading')}</p>
      )}
    </>
  );
}

// ── Tab: Schedule ─────────────────────────────────────────────────────────────

function ScheduleTab() {
  return (
    <div
      style={{
        padding: '20px 24px',
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        maxWidth: 560,
      }}
    >
      <h4 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 700 }}>Automated Backup Schedule</h4>

      <div style={{ display: 'grid', gap: 12, fontSize: 13 }}>
        <div>
          <span style={{ color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, letterSpacing: '0.05em' }}>
            Cron Schedule
          </span>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, marginTop: 4, fontSize: 14 }}>
            {import.meta.env.VITE_BACKUP_CRON ?? '0 22 * * * (daily at 22:00)'}
          </div>
          <div style={{ color: 'var(--muted)', marginTop: 4, fontSize: 12 }}>
            Set via <code>BACKUP_CRON_SCHEDULE</code> in backend/.env
          </div>
        </div>

        <div>
          <span style={{ color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, letterSpacing: '0.05em' }}>
            Replication Snapshots
          </span>
          <div style={{ fontWeight: 600, marginTop: 4 }}>Every 5 minutes (APScheduler)</div>
        </div>

        <div>
          <span style={{ color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, letterSpacing: '0.05em' }}>
            Standalone Worker
          </span>
          <div style={{ marginTop: 4, color: 'var(--text-2)' }}>
            Run <code style={{ fontFamily: 'var(--font-mono)', background: 'var(--surface-3)', padding: '1px 6px', borderRadius: 4 }}>
              python backup_worker.py backup
            </code> for a one-shot backup without APScheduler.
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type TabKey = 'backups' | 'cloud' | 'restore' | 'replication' | 'schedule';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'backups',     label: 'Backups' },
  { key: 'cloud',       label: 'Cloud Uploads' },
  { key: 'restore',     label: 'Restore' },
  { key: 'replication', label: 'Replication' },
  { key: 'schedule',    label: 'Schedule' },
];

export function BackupPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<TabKey>('backups');

  return (
    <div className="admin-page">
      <AdminNav />

      <div className="admin-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <IconDatabase size={22} />
          <h2>{t('backup.title')}</h2>
        </div>
      </div>

      {/* Tab bar */}
      <div
        style={{
          display: 'flex',
          gap: 2,
          borderBottom: '2px solid var(--border)',
          marginBottom: 20,
          overflowX: 'auto',
        }}
      >
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '9px 18px',
              border: 'none',
              borderBottom: tab === t.key ? '2px solid var(--brand)' : '2px solid transparent',
              marginBottom: -2,
              background: 'none',
              fontWeight: tab === t.key ? 700 : 500,
              color: tab === t.key ? 'var(--brand)' : 'var(--text-2)',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              fontSize: 13,
              transition: 'color 120ms',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'backups'     && <BackupsTab />}
      {tab === 'cloud'       && <CloudUploadsTab />}
      {tab === 'restore'     && <RestoreTab />}
      {tab === 'replication' && <ReplicationTab />}
      {tab === 'schedule'    && <ScheduleTab />}
    </div>
  );
}
