export interface CategoryOut {
  id: number;
  name: string;
  parent_id: number | null;
  is_active: boolean;
}

export interface BarcodeOut {
  id: number;
  barcode: string;
  is_primary: boolean;
}

export interface ProductOut {
  id: number;
  name: string;
  description: string | null;
  category_id: number | null;
  price: string;
  tax_rate: string;
  is_active: boolean;
  store_id: number | null;
  barcodes: BarcodeOut[];
}

export interface ProductBarcodeOut {
  product: ProductOut;
  qty_on_hand: number | null;
}
