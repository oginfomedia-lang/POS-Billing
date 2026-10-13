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

  downloadUrl(docId: number): string {
    // Returns the URL; caller uses <a href> or window.open so auth header is added via interceptor
    return `/api/v1/documents/${docId}/download`;
  },

  delete(docId: number) {
    return httpClient.delete<{ message: string }>(`/documents/${docId}`);
  },
};
