// Product and barcode API calls.
import type { ProductOut } from '../../types/product';
import { httpClient } from './httpClient';

// TEMPORARY: GET /products/barcode/<barcode> is being built by Dev 1.
// Until it lands, every scan resolves to this product. Product id 1 must exist
// in the database (with stock) for add-item and checkout to succeed.
const USE_MOCK_BARCODE_LOOKUP = true;

const MOCK_PRODUCT: ProductOut = {
  id: 1,
  name: 'Test Product',
  barcode: '',
  selling_price: '10.00',
  gst_rate: '5.00',
  is_active: true,
};

export async function getProductByBarcode(barcode: string): Promise<ProductOut> {
  if (USE_MOCK_BARCODE_LOOKUP) {
    return { ...MOCK_PRODUCT, barcode };
  }
  const resp = await httpClient.get<ProductOut>(`/products/barcode/${encodeURIComponent(barcode)}`);
  return resp.data;
}
