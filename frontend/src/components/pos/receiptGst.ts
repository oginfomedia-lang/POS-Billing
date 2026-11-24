// The printed bill shows rates and amounts with GST, so the lines add up to the total the customer pays.
// Prices are saved before GST; this works out what to print. Same maths as backend/app/services/ebill_pdf.py.
import type { ReceiptOut } from '../../types/sale.ts';
import { toPaise } from '../../utils/money.ts';

/** paise × (1 + GST %), rounded half up to the paisa, as the server rounds GST. */
export function addGstPaise(paise: number, ratePercent: string | number): number {
  if (!paise) return 0;
  const basisPoints = Math.round(Number(ratePercent) * 100); // 18 % -> 1800
  return Math.floor((paise * (10000 + basisPoints) + 5000) / 10000);
}

export interface GstLine {
  rate: number; // paise, per unit, incl. GST
  amount: number; // paise, qty × rate before discounts, incl. GST
  offer: number;
  manual: number;
}

export interface ReceiptGst {
  lines: GstLine[];
  subtotal: number;
  itemSavings: number;
  billOffer: number;
  reward: number;
}

export function receiptWithGst(r: ReceiptOut): ReceiptGst {
  let billOffer = 0;
  let reward = 0;
  let itemSavings = 0;
  let subtotal = 0;
  const lines = r.items.map((i) => {
    const offerPaise = toPaise(i.offer_discount) || 0;
    const manualPaise = toPaise(i.manual_discount) || 0;
    const rewardPaise = toPaise(i.reward_discount) || 0;
    // The rest of the line's discount is its share of the bill offer.
    const billOfferPaise = Math.max(0, (toPaise(i.discount_amount) || 0) - offerPaise - manualPaise - rewardPaise);
    const line: GstLine = {
      rate: addGstPaise(toPaise(i.unit_price) || 0, i.tax_rate),
      amount: addGstPaise(toPaise(i.line_total) || 0, i.tax_rate),
      offer: addGstPaise(offerPaise, i.tax_rate),
      manual: addGstPaise(manualPaise, i.tax_rate),
    };
    subtotal += line.amount;
    itemSavings += line.offer + line.manual;
    billOffer += addGstPaise(billOfferPaise, i.tax_rate);
    reward += addGstPaise(rewardPaise, i.tax_rate);
    return line;
  });

  // Rounding each line to the paisa can leave the savings a paisa or two off: the biggest saving takes the
  // difference, so subtotal − savings = total exactly.
  const diff = subtotal - itemSavings - billOffer - reward - (toPaise(r.total) || 0);
  if (diff !== 0) {
    if (itemSavings >= billOffer && itemSavings >= reward && itemSavings > 0) itemSavings += diff;
    else if (billOffer >= reward && billOffer > 0) billOffer += diff;
    else if (reward > 0) reward += diff;
  }
  return { lines, subtotal, itemSavings, billOffer, reward };
}
