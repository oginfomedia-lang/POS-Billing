// Review selling prices: products whose price no longer gives the profit wanted, with a suggested price.
// Money is a string (Decimal from the server). "price" is before GST, "price_incl" with GST.

export interface PriceReviewRow {
  product_id: number;
  name: string;
  sku: string | null;
  category_name: string | null;
  uom: string | null;
  cost_price: string; // latest rate paid, before GST
  tax_rate: string;
  mrp: string | null; // incl. GST
  price: string;
  price_incl: string;
  margin_percent: string | null; // profit on cost at the current price
  below_cost: boolean;
  target_percent: string;
  suggested_price: string;
  suggested_price_incl: string;
  suggested_margin_percent: string | null;
  capped_at_mrp: boolean; // the MRP doesn't allow the target profit
  details_pending: boolean; // new product typed on a PO: no selling price yet
  above_mrp: boolean; // current price with GST is above the MRP
}

export interface PriceReviewOut {
  items: PriceReviewRow[];
  default_margin_percent: string;
}
