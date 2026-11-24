// Review selling prices: products whose price no longer gives the profit wanted (cost went up, or the price was
// always too low), with a suggested price from the formula: cost + category target % + GST, never above MRP.
// Apply sets the price; Keep as is hides the row until the cost changes again. ?products=1,2,3 = one delivery.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { applyPrice, getPriceReview, keepPrice } from '../../services/api/priceReviewApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { PriceReviewRow } from '../../types/priceReview';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';

/** What one unit costs the customer: price + GST on it, rounded to the paisa (as on a bill line). */
function withGstPaise(pricePaise: number, taxRate: number): number {
  return pricePaise + Math.round((pricePaise * taxRate) / 100);
}

function pct(value: string | number | null): string {
  return value === null ? '—' : `${Number(value).toFixed(2)}%`;
}

export function PriceReviewPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const productIds = (params.get('products') || '')
    .split(',')
    .map((s) => parseInt(s, 10))
    .filter((n) => Number.isFinite(n) && n > 0);
  const oneDelivery = productIds.length > 0;

  const [rows, setRows] = useState<PriceReviewRow[]>([]);
  const [defaultMargin, setDefaultMargin] = useState('');
  const [typed, setTyped] = useState<Record<number, string>>({}); // product_id → price before GST
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const out = await getPriceReview(oneDelivery ? productIds : undefined);
      setRows(out.items);
      setDefaultMargin(out.default_margin_percent);
      setTyped(Object.fromEntries(out.items.map((r) => [r.product_id, r.suggested_price])));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [params.get('products')]);

  function finish(row: PriceReviewRow, message: string) {
    setRows((current) => current.filter((r) => r.product_id !== row.product_id));
    setDone(message);
  }

  async function apply(row: PriceReviewRow) {
    const price = typed[row.product_id] ?? row.suggested_price;
    setBusyId(row.product_id);
    setError('');
    try {
      const out = await applyPrice(row.product_id, paiseToString(toPaise(price)));
      finish(row, t('priceReview.applied', { name: row.name, price: formatRupees(out.price_incl) }));
    } catch (err) {
      setError(`${row.name}: ${getErrorMessage(err)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function keep(row: PriceReviewRow) {
    setBusyId(row.product_id);
    setError('');
    try {
      await keepPrice(row.product_id);
      finish(row, t('priceReview.kept', { name: row.name }));
    } catch (err) {
      setError(`${row.name}: ${getErrorMessage(err)}`);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="admin-page">
      <AdminNav />
      <div className="admin-header">
        <h2>{t('priceReview.title')}</h2>
      </div>

      <p className="hint-text">{t('priceReview.hint', { pct: defaultMargin ? Number(defaultMargin) : 10 })}</p>
      {oneDelivery && (
        <p className="hint-text">
          {t('priceReview.oneDelivery')} <Link to="/admin/price-review">{t('priceReview.showAll')}</Link>
        </p>
      )}
      {error && <div className="page-error">{error}</div>}
      {done && <div className="notice-bar">{done}</div>}
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('priceReview.colProduct')}</th>
              <th className="num">{t('priceReview.colCost')}</th>
              <th className="num">{t('priceReview.colMrp')}</th>
              <th className="num">{t('priceReview.colNow')}</th>
              <th className="num">{t('priceReview.colTarget')}</th>
              <th className="num">{t('priceReview.colSuggested')}</th>
              <th>{t('priceReview.colNewPrice')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {!loading && rows.length === 0 && (
              <tr><td colSpan={8} className="empty-row">{t(oneDelivery ? 'priceReview.emptyDelivery' : 'priceReview.empty')}</td></tr>
            )}
            {rows.map((r) => {
              const text = typed[r.product_id] ?? '';
              const paise = toPaise(text);
              const valid = Number.isFinite(paise) && paise >= 0;
              const inclPaise = valid ? withGstPaise(paise, Number(r.tax_rate)) : NaN;
              const costPaise = Number(r.cost_price) * 100;
              const newMargin = valid && costPaise > 0 ? ((paise - costPaise) / costPaise) * 100 : null;
              const overMrp = valid && r.mrp !== null && inclPaise > toPaise(r.mrp);
              const busy = busyId === r.product_id;
              return (
                <tr key={r.product_id}>
                  <td>
                    <strong>{r.name}</strong>
                    {r.details_pending && (
                      <span className="status-badge badge-warning" style={{ marginLeft: 6 }}>{t('priceReview.newProduct')}</span>
                    )}
                    {r.above_mrp && (
                      <span className="status-badge badge-error" style={{ marginLeft: 6 }}>{t('priceReview.aboveMrp')}</span>
                    )}
                    <div className="hint-text">
                      {[r.category_name, r.sku, `${t('priceReview.gst')} ${Number(r.tax_rate)}%`].filter(Boolean).join(' · ')}
                    </div>
                  </td>
                  <td className="num">{formatRupees(r.cost_price)}</td>
                  <td className="num">{r.mrp !== null ? formatRupees(r.mrp) : '—'}</td>
                  <td className="num">
                    {formatRupees(r.price_incl)}
                    <div className={r.below_cost ? 'text-danger' : 'hint-text'}>
                      {r.below_cost ? t('priceReview.loss', { pct: pct(r.margin_percent) }) : pct(r.margin_percent)}
                    </div>
                  </td>
                  <td className="num">{pct(r.target_percent)}</td>
                  <td className="num">
                    <strong>{formatRupees(r.suggested_price_incl)}</strong>
                    <div className="hint-text">{pct(r.suggested_margin_percent)}</div>
                    {r.capped_at_mrp && <span className="status-badge badge-warning">{t('priceReview.capped')}</span>}
                  </td>
                  <td>
                    <input
                      className="field-input"
                      type="number"
                      min="0"
                      step="0.01"
                      style={{ maxWidth: 120 }}
                      value={text}
                      aria-label={t('priceReview.colNewPrice')}
                      onChange={(e) => setTyped((cur) => ({ ...cur, [r.product_id]: e.target.value }))}
                    />
                    <div className={overMrp ? 'text-danger' : 'hint-text'} style={overMrp ? {fontWeight: 700 } : undefined }>
                      {valid ? t('priceReview.withGst', { amount: formatRupees(paiseToString(inclPaise)) }) : '—'}
                      {newMargin !== null && ` · ${pct(newMargin)}`}
                      {overMrp && ` · ${t('priceReview.overMrp')}`}
                    </div>
                  </td>
                  <td className="table-actions">
                    <button className="btn-sm btn-primary" disabled={busy || !valid || overMrp} onClick={() => apply(r)}>
                      {t('priceReview.apply')}
                    </button>
                    {/* A new product has no price to keep, and a price above MRP can't be kept. */}
                    {!r.details_pending && !r.above_mrp && (
                      <button className="btn-sm" disabled={busy} onClick={() => keep(r)}>{t('priceReview.keep')}</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
