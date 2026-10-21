// Offline bill maths and shapes: the cart priced with the catalogue's offers, the bill saved for upload, and the
// receipt (same layout as online bills: components/pos/ReceiptView.tsx).
import type { ReceiptOut, SaleItemOut } from '../types/sale.ts';
import { Dec, money } from './decimal.ts';
import { activeOffers, lineSaving, priceBill, type PricedBill } from './pricing.ts';
import type { OfflineBill, OfflineBillItem, OfflineCatalog, OfflineProduct } from './types.ts';

export interface PricedCart {
  bill: PricedBill;
  items: OfflineBillItem[];
}

export function priceCart(lines: { product: OfflineProduct; qty: string }[], catalog: OfflineCatalog, now: Date): PricedCart {
  const bill = priceBill(
    lines.map((l) => ({
      product_id: l.product.id, category_id: l.product.category_id, unit_price: l.product.price,
      tax_rate: l.product.tax_rate, qty: l.qty,
    })),
    activeOffers(catalog.offers, now),
    catalog.categories,
  );
  const items = lines.map((l, i): OfflineBillItem => ({
    product_id: l.product.id,
    product_name: l.product.name,
    qty: l.qty,
    unit_price: l.product.price,
    tax_rate: l.product.tax_rate,
    mrp: l.product.mrp,
    hsn_code: l.product.hsn_code,
    uom: l.product.uom,
    is_variable_weight: l.product.is_variable_weight,
    ...bill.lines[i],
  }));
  return { bill, items };
}

export function changeDue(total: string, tendered: string): string {
  return money(Dec.of(tendered).sub(total)).toString();
}

function qtyNumber(qty: string): number {
  return Dec.of(qty).toNumber();
}

/** Sum of the quantities, shown without trailing zeros: "10", "23.5" (as the server's receipt_service.total_qty). */
function totalQty(items: OfflineBillItem[]): string {
  const total = Dec.sum(items.map((i) => Dec.of(i.qty))).quantize(3);
  return String(total.toNumber());
}

export function toReceipt(bill: OfflineBill): ReceiptOut {
  const items: SaleItemOut[] = bill.items.map((i, n) => ({
    id: n + 1,
    product_id: i.product_id,
    product_name: i.product_name,
    unit_price: i.unit_price,
    tax_rate: i.tax_rate,
    mrp: i.mrp,
    hsn_code: i.hsn_code,
    qty: qtyNumber(i.qty),
    line_total: i.line_total,
    discount_amount: i.discount_amount,
    offer_name: i.offer_name,
    offer_discount: i.offer_discount,
    manual_discount: '0.00',
    manual_discount_reason: null,
    reward_discount: '0.00',
    tax_amount: i.tax_amount,
    saving: lineSaving(i.mrp, i.qty, i.line_total, i.discount_amount, i.tax_amount),
    is_variable_weight: i.is_variable_weight,
    uom: i.uom,
  }));
  return {
    sale_id: 0,
    item_lines: items.length,
    total_qty: totalQty(bill.items),
    bill_number: bill.bill_number,
    store_name: bill.store.name,
    store_address: bill.store.address,
    store_phone: bill.store.phone,
    store_gstin: bill.store.gstin,
    counter_code: bill.counter_code,
    cashier_name: bill.cashier_name,
    customer_mobile: null,
    completed_at: bill.billed_at,
    items,
    subtotal: bill.subtotal,
    discount_amount: bill.discount_amount,
    bill_offer_name: bill.bill_offer_name,
    bill_offer_discount: bill.bill_offer_discount,
    tax_amount: bill.tax_amount,
    total: bill.total,
    total_saving: money(Dec.sum(items.map((i) => Dec.of(i.saving)))).toString(),
    points_redeemed: 0,
    reward_discount: '0.00',
    points_earned: 0,
    points_balance: null,
    gst_summary: [],
    payments: [{
      id: 1, method: 'cash', amount: bill.total, reference: null, tendered: bill.cash_tendered,
      change_due: bill.change_due, created_at: bill.billed_at,
    }],
    receipt_header: bill.settings.receipt_header,
    receipt_footer: bill.settings.receipt_footer,
    receipt_footer_mr: bill.settings.receipt_footer_mr,
    fssai_number: bill.settings.fssai_number,
    ebill: null,
  };
}
