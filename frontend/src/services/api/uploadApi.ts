import type { DocumentEntityType, SupplierDocumentOut } from '../../types/api';
import { httpClient } from './httpClient';

export const uploadApi = {
  list(entityType: DocumentEntityType, entityId: number) {
    return httpClient.get<SupplierDocumentOut[]>('/documents', {
      params: { entity_type: entityType, entity_id: entityId },
    });
  },

  upload(
    file: File,
    entityType: DocumentEntityType,
    entityId: number,
    documentLabel?: string,
  ) {
    const form = new FormData();
    form.append('file', file);
    form.append('entity_type', entityType);
    form.append('entity_id', String(entityId));
    if (documentLabel) form.append('document_label', documentLabel);
    return httpClient.post<SupplierDocumentOut>('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  /** Opens a stored document (e.g. a supplier's bill); the request carries the login.
   *  In the desktop app it opens in Windows' own viewer (the app window never opens new windows); in a plain
   *  browser, in a new tab. Throws with a readable reason if it can't be opened. */
  async open(docId: number): Promise<void> {
    const resp = await httpClient.get<Blob>(`/documents/${docId}/download`, { responseType: 'blob' });
    const blob = resp.data;
    if (typeof window !== 'undefined' && window.posBridge?.openDocument) {
      const problem = await window.posBridge.openDocument(new Uint8Array(await blob.arrayBuffer()), blob.type);
      if (problem) throw new Error(problem);
      return;
    }
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },

  downloadUrl(docId: number): string {
    // Returns the URL; caller uses <a href> or window.open so auth header is added via interceptor
    return `/api/v1/documents/${docId}/download`;
  },

  delete(docId: number) {
    return httpClient.delete<{ message: string }>(`/documents/${docId}`);
  },
};
