import type { CategoryOut, ProductBarcodeOut, ProductOut } from '../../types/product';
import type { PagedResponse } from '../../types/api';
import { httpClient } from './httpClient';

export async function getProductByBarcode(barcode: string): Promise<ProductBarcodeOut> {
  const resp = await httpClient.get<ProductBarcodeOut>(`/products/barcode/${encodeURIComponent(barcode)}`);
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
  price: number;
  tax_rate?: number;
  category_id?: number | null;
  description?: string | null;
  store_id?: number | null;
  barcodes?: string[];
}): Promise<ProductOut> {
  const resp = await httpClient.post<ProductOut>('/products', data);
  return resp.data;
}

export async function updateProduct(
  id: number,
  data: Partial<{ name: string; price: number; tax_rate: number; is_active: boolean; category_id: number | null }>,
): Promise<ProductOut> {
  const resp = await httpClient.put<ProductOut>(`/products/${id}`, data);
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
