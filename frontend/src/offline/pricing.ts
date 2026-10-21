// Bill pricing for offline billing: the same rules as the server, so a bill made without the server costs what
// it would have cost online. Mirrors backend app/services/pricing_service.py and discount_service.choose_best_offer
// (only ONE automatic offer per bill: whichever saves the most). Checked against the server's own results in
// tests/unit/offlinePricing.test.ts (fixtures written by backend tests/integration/test_offline_pricing_cases.py).
import { Dec, money } from './decimal.ts';

export type DiscountType = 'percentage' | 'fixed' | 'buy_x_get_y' | 'qty_price';
export type DiscountScope = 'bill' | 'product' | 'category';

export interface OfflineOffer {
  id: number;
  name: string;
  discount_type: DiscountType;
  value: string;
  scope: DiscountScope;
  product_id: number | null;
  category_id: number | null;
  min_bill_amount: string | null;
  max_discount_amount: string | null;
  buy_qty: number | null;
  get_qty: number | null;
  starts_at: string | null;
  ends_at: string | null;
}

/** One line to price: the product's catalogue values and the quantity. */
export interface LineInput {
  product_id: number;
  category_id: number | null;
  unit_price: string;
  tax_rate: string;
  qty: string;
}

export interface PricedLine {
  line_total: string;
  offer_id: number | null;
  offer_name: string | null;
  offer_discount: string; // item offer only
  discount_amount: string; // item offer, or this line's share of the bill offer
  tax_amount: string;
}

export interface PricedBill {
  lines: PricedLine[];
  bill_offer_id: number | null;
  bill_offer_name: string | null;
  bill_offer_discount: string;
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  total: string;
}

const HUNDRED = Dec.of(100);

/** line_amounts(): (line_total, tax_amount). Prices exclude GST; GST is on (line_total − discount). */
export function lineAmounts(unitPrice: string | Dec, qty: string | Dec, taxRate: string | Dec, discount: string | Dec = '0'): [Dec, Dec] {
  const lineTotal = money(Dec.of(unitPrice).mul(Dec.of(qty)));
  const taxable = lineTotal.sub(money(discount));
  return [lineTotal, money(taxable.mul(Dec.of(taxRate)).div(HUNDRED))];
}

function itemDiscount(type: DiscountType, value: Dec, lineTotal: Dec, qty: Dec, cap: Dec | null): Dec {
  let amount: Dec;
  if (type === 'percentage') {
    amount = lineTotal.mul(value).div(HUNDRED);
    if (cap) amount = Dec.min(amount, cap);
  } else {
    amount = value.mul(qty);
  }
  return money(Dec.min(amount, lineTotal));
}

function billDiscount(type: DiscountType, value: Dec, amount: Dec, cap: Dec | null): Dec {
  let off: Dec;
  if (type === 'percentage') {
    off = amount.mul(value).div(HUNDRED);
    if (cap) off = Dec.min(off, cap);
  } else {
    off = value;
  }
  return money(Dec.min(off, amount));
}

function buyXGetY(buyQty: number, getQty: number, lineTotal: Dec): Dec {
  return money(lineTotal.mul(getQty).div(buyQty + getQty));
}

function qtyPrice(unitPrice: Dec, qty: Dec, taxRate: Dec, bundleQty: number, bundlePrice: Dec, lineTotal: Dec): Dec {
  const bundles = qty.div(bundleQty).floor();
  const bundleExGst = bundlePrice.mul(HUNDRED).div(HUNDRED.add(taxRate));
  const savingPerBundle = unitPrice.mul(bundleQty).sub(bundleExGst);
  if (bundles === 0n || !savingPerBundle.gt(0)) return money(0);
  return money(Dec.min(savingPerBundle.mul(bundles.toString()), lineTotal));
}

/** allocate(): split amount across lines by weight; the rounding remainder goes to the largest line. */
export function allocate(amount: Dec, weights: Dec[]): Dec[] {
  const total = Dec.sum(weights);
  const rounded = money(amount);
  if (rounded.isZero() || total.isZero()) return weights.map(() => money(0));
  const shares = weights.map((w) => money(rounded.mul(w).div(total)));
  let biggest = 0;
  weights.forEach((w, i) => { if (w.gt(weights[biggest])) biggest = i; });
  shares[biggest] = shares[biggest].add(rounded.sub(Dec.sum(shares)));
  return shares;
}

/** The category and every parent above it (stops on a loop). */
function withAncestors(categoryId: number | null, parents: Record<string, number | null>): Set<number> {
  const family = new Set<number>();
  let id = categoryId;
  while (id !== null && id !== undefined && !family.has(id)) {
    family.add(id);
    id = parents[String(id)] ?? null;
  }
  return family;
}

function itemOfferAmount(o: OfflineOffer, line: LineInput, lineTotal: Dec): Dec {
  if (o.discount_type === 'buy_x_get_y') return buyXGetY(o.buy_qty ?? 0, o.get_qty ?? 0, lineTotal);
  if (o.discount_type === 'qty_price') {
    return qtyPrice(Dec.of(line.unit_price), Dec.of(line.qty), Dec.of(line.tax_rate), o.buy_qty ?? 1, Dec.of(o.value), lineTotal);
  }
  return itemDiscount(o.discount_type, Dec.of(o.value), lineTotal, Dec.of(line.qty),
    o.max_discount_amount === null ? null : Dec.of(o.max_discount_amount));
}

/** Offers that apply at `now` (starts_at ≤ now < ends_at), as the server's active_for_store, in id order. */
export function activeOffers(offers: OfflineOffer[], now: Date): OfflineOffer[] {
  const t = now.getTime();
  return offers
    .filter((o) => (o.starts_at === null || Date.parse(o.starts_at) <= t) && (o.ends_at === null || Date.parse(o.ends_at) > t))
    .sort((a, b) => a.id - b.id);
}

/** Prices a whole bill with the offers given (already filtered with activeOffers). Mirrors billing_service._recalculate
 * for a bill without manual discounts or reward points (neither is available offline). */
export function priceBill(lines: LineInput[], offers: OfflineOffer[], categories: Record<string, number | null>): PricedBill {
  const lineTotals = lines.map((l) => money(Dec.of(l.unit_price).mul(Dec.of(l.qty))));
  const room = lineTotals; // no manual discounts offline
  const withGst = Dec.sum(lines.map((l, i) => room[i].add(lineAmounts(l.unit_price, l.qty, l.tax_rate, '0')[1])));
  const billAmount = Dec.sum(room);
  const families = lines.map((l) => withAncestors(l.category_id, categories));

  let best: { offer: OfflineOffer | null; amount: Dec; perLine: Dec[]; isBill: boolean } = {
    offer: null, amount: money(0), perLine: lines.map(() => money(0)), isBill: false,
  };
  for (const o of offers) {
    if (o.scope === 'bill') {
      if (!billAmount.gt(0) || withGst.lt(o.min_bill_amount ?? '0')) continue;
      const off = billDiscount(o.discount_type, Dec.of(o.value), billAmount,
        o.max_discount_amount === null ? null : Dec.of(o.max_discount_amount));
      if (off.gt(best.amount)) best = { offer: o, amount: off, perLine: allocate(off, room), isBill: true };
    } else {
      const perLine = lines.map((l, i) => {
        const matches = o.scope === 'product' ? o.product_id === l.product_id
          : o.scope === 'category' && o.category_id !== null && families[i].has(o.category_id);
        return matches ? Dec.min(itemOfferAmount(o, l, lineTotals[i]), room[i]) : money(0);
      });
      const total = Dec.sum(perLine);
      if (total.gt(best.amount)) best = { offer: o, amount: total, perLine, isBill: false };
    }
  }

  const priced = lines.map((l, i) => {
    const off = best.perLine[i];
    const onLine = !best.isBill && off.gt(0);
    const [lineTotal, tax] = lineAmounts(l.unit_price, l.qty, l.tax_rate, off);
    return {
      line_total: lineTotal.toString(),
      offer_id: onLine ? best.offer!.id : null,
      offer_name: onLine ? best.offer!.name : null,
      offer_discount: (onLine ? off : money(0)).toString(),
      discount_amount: money(off).toString(),
      tax_amount: tax.toString(),
    };
  });
  const subtotal = money(Dec.sum(priced.map((p) => Dec.of(p.line_total))));
  const discount = money(Dec.sum(priced.map((p) => Dec.of(p.discount_amount))));
  const tax = money(Dec.sum(priced.map((p) => Dec.of(p.tax_amount))));
  return {
    lines: priced,
    bill_offer_id: best.isBill ? best.offer!.id : null,
    bill_offer_name: best.isBill ? best.offer!.name : null,
    bill_offer_discount: (best.isBill ? best.amount : money(0)).toString(),
    subtotal: subtotal.toString(),
    discount_amount: discount.toString(),
    tax_amount: tax.toString(),
    total: money(subtotal.sub(discount).add(tax)).toString(),
  };
}

/** line_saving(): MRP × qty − what was paid (incl. GST); without an MRP, the discount. */
export function lineSaving(mrp: string | null, qty: string, lineTotal: string, discount: string, tax: string): string {
  if (mrp === null) return money(discount).toString();
  const paid = Dec.of(lineTotal).sub(discount).add(tax);
  return Dec.max(money(Dec.of(mrp).mul(qty).sub(paid)), money(0)).toString();
}
