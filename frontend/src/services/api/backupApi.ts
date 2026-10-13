// Backup management API calls.
import type {
  BackupRunOut,
  CloudUploadAttemptOut,
  PagedResponse,
  ReplicationStatusOut,
  RestoreRecordOut,
} from '../../types/api';
import { httpClient } from './httpClient';

export const backupApi = {
  list(page = 1, perPage = 20) {
    return httpClient.get<PagedResponse<BackupRunOut>>('/backups', {
      params: { page, per_page: perPage },
    });
  },

  create() {
    return httpClient.post<BackupRunOut>('/backups');
  },

  verify(id: number) {
    return httpClient.post<BackupRunOut>(`/backups/${id}/verify`);
  },

  delete(id: number) {
    return httpClient.delete<{ id: number; status: string }>(`/backups/${id}`);
  },

  /** Download a backup file — returns raw blob for Save-As dialog. */
  downloadBlob(id: number) {
    return httpClient.get(`/backups/${id}/download`, {
      responseType: 'blob',
      timeout: 120_000,
    });
  },

  // ── Cloud upload ──────────────────────────────────────────────────────────

  uploadToCloud(id: number, provider = 's3') {
    return httpClient.post<CloudUploadAttemptOut>(`/backups/${id}/upload`, { provider });
  },

  listUploads(id: number) {
    return httpClient.get<CloudUploadAttemptOut[]>(`/backups/${id}/uploads`);
  },

  // ── Replication ───────────────────────────────────────────────────────────

  getReplication() {
    return httpClient.get<ReplicationStatusOut>('/backups/replication');
  },

  takeReplicationSnapshot() {
    return httpClient.post('/backups/replication/snapshot');
  },

  // ── Restore ───────────────────────────────────────────────────────────────

  triggerRestore(id: number, targetDb: string) {
    return httpClient.post<RestoreRecordOut>(`/backups/${id}/restore`, { target_db: targetDb });
  },

  listRestores(page = 1, perPage = 20) {
    return httpClient.get<PagedResponse<RestoreRecordOut>>('/backups/restores', {
      params: { page, per_page: perPage },
    });
  },

  getRestore(restoreId: number) {
    return httpClient.get<RestoreRecordOut>(`/backups/restores/${restoreId}`);
  },
};
