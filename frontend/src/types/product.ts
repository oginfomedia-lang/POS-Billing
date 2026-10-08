export type BarcodeType = 'MANUFACTURER' | 'IN_HOUSE' | 'PRICE_EMBEDDED';
export type UOMType = 'pcs' | 'kg' | 'g' | 'ltr' | 'ml' | 'pack';

export interface CategoryOut {
  id: number;
  name: string;
  parent_id: number | null;
  is_active: boolean;
}

export interface BarcodeOut {
  id: number;
  barcode: string;
  barcode_type: BarcodeType;
  is_primary: boolean;
  created_at?: string;
}

export interface ProductOut {
  id: number;
  sku: string;
  name: string;
  description: string | null;
  category_id: number | null;
  price: string; // head-office price
  /** This branch's own price, when the request named a store (null = sells at `price`). */
  store_price?: string | null;
  tax_rate: string;
  mrp: string | null; // printed MRP, incl. GST (per unit, or per kg if weighed)
  hsn_code: string | null;
  uom: UOMType;
  is_variable_weight: boolean;
  is_active: boolean;
  store_id: number | null;
  barcodes: BarcodeOut[];
}

export interface ProductBarcodeOut {
  product: ProductOut;
  scanned_barcode?: string;
  is_variable_weight?: boolean;
  weight_grams?: number | null;
  weight_kg?: number | null;
  unit_price?: string | number | null;
  calculated_price?: string | number | null;
  qty_on_hand: number | null;
}
