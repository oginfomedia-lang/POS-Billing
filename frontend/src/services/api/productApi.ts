import axios from 'axios';
import type {
  BarcodeOut,
  BarcodeType,
  CategoryOut,
  ImportOptions,
  ImportPreview,
  ImportResult,
  ProductBarcodeOut,
  ProductOut,
  UOMType,
} from '../../types/product';
import type { PagedResponse } from '../../types/api';
import { httpClient } from './httpClient';

/**
 * Scanner lookup. A weighing-scale sticker comes back with the loose item and `weight_kg`.
 * storeId = the bill's store (price-in-barcode stickers use that store's price).
 */
export async function getProductByBarcode(barcode: string, storeId?: number): Promise<ProductBarcodeOut> {
  const resp = await httpClient.get<ProductBarcodeOut>('/pos/scan', { params: { barcode, store_id: storeId } });
  return resp.data;
}

export async function scanProduct(barcode: string, storeId?: number): Promise<ProductBarcodeOut> {
  return getProductByBarcode(barcode, storeId);
}

export async function listProducts(params?: {
  page?: number;
  per_page?: number;
  active_only?: boolean;
  category_id?: number;
  /** Name or SKU contains, or exact barcode. */
  q?: string;
  /** Only active or only deactivated products; omit for all. */
  status?: 'active' | 'inactive';
  /** Branch: shared products + that branch's own, with its store_price filled in. */
  store_id?: number;
}): Promise<PagedResponse<ProductOut>> {
  const resp = await httpClient.get<PagedResponse<ProductOut>>('/products', { params });
  return resp.data;
}

export async function createProduct(data: {
  name: string;
  sku?: string;
  price: number;
  tax_rate?: number;
  mrp?: number | null;
  hsn_code?: string | null;
  uom?: UOMType;
  category_id?: number | null;
  description?: string | null;
  is_variable_weight?: boolean;
  /** Loose items: the item code set on the weighing scale. */
  plu_code?: string | null;
  store_id?: number | null;
  supplier_id?: number | null;
  barcodes?: (string | { barcode: string; barcode_type?: BarcodeType })[];
}): Promise<ProductOut> {
  const resp = await httpClient.post<ProductOut>('/products', data);
  return resp.data;
}

export async function updateProduct(
  id: number,
  data: Partial<{
    name: string;
    sku: string;
    price: number;
    tax_rate: number;
    /** null clears it; leave out to keep. */
    mrp: number | null;
    hsn_code: string | null;
    uom: UOMType;
    is_variable_weight: boolean;
    /** null clears it; leave out to keep. */
    plu_code: string | null;
    is_active: boolean;
    category_id: number | null;
    /** null removes it; leave out to keep. */
    supplier_id: number | null;
    barcodes: (string | { barcode: string; barcode_type?: BarcodeType })[];
  }>,
): Promise<ProductOut> {
  const resp = await httpClient.put<ProductOut>(`/products/${id}`, data);
  return resp.data;
}


export async function addBarcode(
  id: number,
  barcode: string,
  barcode_type: BarcodeType = 'MANUFACTURER',
): Promise<BarcodeOut> {
  const resp = await httpClient.post<BarcodeOut>(`/products/${id}/barcodes`, {
    barcode,
    barcode_type,
  });
  return resp.data;
}

export async function deleteBarcode(id: number, barcode: string): Promise<void> {
  await httpClient.delete(`/products/${id}/barcodes/${encodeURIComponent(barcode)}`);
}

export async function getProduct(id: number, storeId?: number | null): Promise<ProductOut> {
  const resp = await httpClient.get<ProductOut>(`/products/${id}`, { params: { store_id: storeId ?? undefined } });
  return resp.data;
}

/** A fresh unused in-house code for a product that isn't saved yet. */
export async function generateNewInhouseBarcode(): Promise<string> {
  const resp = await httpClient.post<{ barcode: string }>('/products/barcodes/generate');
  return resp.data.barcode;
}

export async function generateInhouseBarcode(id: number): Promise<BarcodeOut> {
  const resp = await httpClient.post<BarcodeOut>(`/products/${id}/generate-inhouse-barcode`);
  return resp.data;
}

export async function listCategories(activeOnly = false): Promise<CategoryOut[]> {
  const resp = await httpClient.get<CategoryOut[]>('/categories', {
    params: { active_only: activeOnly },
  });
  return resp.data;
}

export async function createCategory(data: { name: string; parent_id?: number | null }): Promise<CategoryOut> {
  const resp = await httpClient.post<CategoryOut>('/categories', data);
  return resp.data;
}

// ── Bulk import (CSV / Excel) ──

/** A big file can take a while to check and save. */
const IMPORT_TIMEOUT_MS = 120_000;

function importForm(file: File, options: ImportOptions): FormData {
  const form = new FormData();
  form.append('file', file);
  if (options.store_id != null) form.append('store_id', String(options.store_id));
  form.append('sold_in', options.sold_in);
  form.append('generate_barcodes', String(options.generate_barcodes));
  return form;
}

/** Saves the sample Excel sheet (right columns, barcode columns as text) to the user's computer. */
export async function downloadImportTemplate(): Promise<void> {
  const resp = await httpClient.get<Blob>('/products/import/template', { responseType: 'blob' });
  const url = URL.createObjectURL(resp.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'product-import-template.xlsx';
  link.click();
  URL.revokeObjectURL(url);
}

/** Checks every row and says what would happen. Saves nothing. */
export async function previewImport(file: File, options: ImportOptions): Promise<ImportPreview> {
  const resp = await httpClient.post<ImportPreview>('/products/import/preview', importForm(file, options), {
    timeout: IMPORT_TIMEOUT_MS,
  });
  return resp.data;
}

/** Imports the file (all or nothing). If rows have errors nothing is saved and the fresh preview comes back. */
export async function runImport(
  file: File,
  options: ImportOptions,
): Promise<{ result: ImportResult } | { preview: ImportPreview }> {
  try {
    const resp = await httpClient.post<ImportResult>('/products/import', importForm(file, options), {
      timeout: IMPORT_TIMEOUT_MS,
    });
    return { result: resp.data };
  } catch (err) {
    const preview = axios.isAxiosError(err) ? (err.response?.data as { preview?: ImportPreview })?.preview : undefined;
    if (preview) return { preview };
    throw err;
  }
}
