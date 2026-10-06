import type { BarcodeOut, BarcodeType, CategoryOut, ProductBarcodeOut, ProductOut } from '../../types/product';
import type { PagedResponse } from '../../types/api';
import { httpClient } from './httpClient';

export async function getProductByBarcode(barcode: string): Promise<ProductBarcodeOut> {
  const resp = await httpClient.get<ProductBarcodeOut>(`/pos/scan?barcode=${encodeURIComponent(barcode)}`);
  return resp.data;
}

export async function scanProduct(barcode: string): Promise<ProductBarcodeOut> {
  const resp = await httpClient.get<ProductBarcodeOut>(`/pos/scan?barcode=${encodeURIComponent(barcode)}`);
  return resp.data;
}

export async function listProducts(params?: {
  page?: number;
  per_page?: number;
  active_only?: boolean;
  category_id?: number;
}): Promise<PagedResponse<ProductOut>> {
  const resp = await httpClient.get<PagedResponse<ProductOut>>('/products', { params });
  return resp.data;
}

export async function createProduct(data: {
  name: string;
  sku?: string;
  price: number;
  tax_rate?: number;
  category_id?: number | null;
  description?: string | null;
  is_variable_weight?: boolean;
  store_id?: number | null;
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
    is_variable_weight: boolean;
    is_active: boolean;
    category_id: number | null;
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
