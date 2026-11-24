// Review selling prices (admin / manager).
import type { PriceReviewOut, PriceReviewRow } from '../../types/priceReview';
import { httpClient } from './httpClient';

/** Products to review; productIds = only these (e.g. the products of one goods receipt). */
export async function getPriceReview(productIds?: number[]): Promise<PriceReviewOut> {
  const params = productIds && productIds.length ? { product_ids: productIds.join(',') } : undefined;
  const resp = await httpClient.get<PriceReviewOut>('/price-review', { params });
  return resp.data;
}

/** Set the selling price (before GST). */
export async function applyPrice(productId: number, price: string): Promise<PriceReviewRow> {
  const resp = await httpClient.post<PriceReviewRow>(`/price-review/${productId}/apply`, { price });
  return resp.data;
}

/** Keep the current price; asked again when the cost changes. */
export async function keepPrice(productId: number): Promise<void> {
  await httpClient.post(`/price-review/${productId}/keep`);
}
