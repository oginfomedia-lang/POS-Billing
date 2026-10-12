// Backup management API calls.
import type { BackupRunOut, PagedResponse } from '../../types/api';
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

  /**
   * Download a backup file.  Uses a long timeout and returns the raw blob so
   * the caller can trigger a browser Save-As dialog.
   */
  downloadBlob(id: number) {
    return httpClient.get(`/backups/${id}/download`, {
      responseType: 'blob',
      timeout: 120_000,
    });
  },
};
