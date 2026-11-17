// Accounting for Tally: Day Book of vouchers, GST output against input, Tally ledger names, Tally XML download.
import type { ParseKeys } from 'i18next';
import { type FormEvent, Fragment, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AdminNav } from '../../components/admin/AdminNav';
import { useAuth } from '../../hooks/useAuth';
import { downloadTallyXml, getDayBook, getGstSummary, getLedgers, saveLedgers } from '../../services/api/accountingApi';
import { getErrorMessage } from '../../services/api/httpClient';
import { useStoreContext } from '../../store/storeContext';
import type { DayBookOut, GstHeadRow, GstSummaryOut, TallyLedgers, VoucherType } from '../../types/accounting';
import { isoDateIst, monthStartIst } from '../../utils/format';
import { formatRupees } from '../../utils/money';

type Tab = 'daybook' | 'gst' | 'ledgers';

/** First and last day of last month, YYYY-MM-DD. */
function lastMonth(): [string, string] {
  const [y, m] = monthStartIst().split('-').map(Number);
  const prev = m === 1 ? [y - 1, 12] : [y, m - 1];
  const days = new Date(prev[0], prev[1], 0).getDate();
  const ym = `${prev[0]}-${String(prev[1]).padStart(2, '0')}`;
  return [`${ym}-01`, `${ym}-${String(days).padStart(2, '0')}`];
}

const QUICK_RANGES: { label: ParseKeys; range: () => [string, string] }[] = [
  { label: 'reports.today', range: () => [isoDateIst(), isoDateIst()] },
  { label: 'reports.yesterday', range: () => [isoDateIst(1), isoDateIst(1)] },
  { label: 'reports.thisMonth', range: () => [monthStartIst(), isoDateIst()] },
  { label: 'accounting.lastMonth', range: lastMonth },
];

const LEDGER_FIELDS: (keyof TallyLedgers)[] = [
  'cash', 'upi', 'card', 'bank', 'udhari', 'sales', 'sales_return', 'purchase', 'purchase_return',
  'output_cgst', 'output_sgst', 'input_cgst', 'input_sgst', 'input_igst', 'freight', 'round_off',
];

/** ₹ amount, or blank for a zero (debit / credit columns). */
function amt(value: string): string {
  return Number(value) ? formatRupees(value) : '\u2014';
}

function GstTable({ rows, total, showIgst }: { rows: GstHeadRow[]; total: GstHeadRow; showIgst: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="table-card">
      <table className="data-table">
        <thead>
          <tr>
            <th>{t('accounting.colRate')}</th><th className="num">{t('accounting.colTaxable')}</th>
            <th className="num">CGST</th><th className="num">SGST</th>{showIgst && <th className="num">IGST</th>}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={showIgst ? 5 : 4} className="empty-row">{t('accounting.nothing')}</td></tr>}
          {rows.map((r) => (
            <tr key={r.tax_rate}>
              <td>{Number(r.tax_rate)}%</td><td className="num">{formatRupees(r.taxable)}</td>
              <td className="num">{formatRupees(r.cgst)}</td><td className="num">{formatRupees(r.sgst)}</td>
              {showIgst && <td className="num">{formatRupees(r.igst)}</td>}
            </tr>
          ))}
          {rows.length > 0 && (
            <tr style={{ fontWeight: 700 }}>
              <td>{t('accounting.total')}</td><td className="num">{formatRupees(total.taxable)}</td>
              <td className="num">{formatRupees(total.cgst)}</td><td className="num">{formatRupees(total.sgst)}</td>
              {showIgst && <td className="num">{formatRupees(total.igst)}</td>}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function AccountingPage() {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();
  const storeId = useStoreContext((s) => s.selectedId);
  const [tab, setTab] = useState<Tab>('daybook');
  const [dateFrom, setDateFrom] = useState(monthStartIst());
  const [dateTo, setDateTo] = useState(isoDateIst());
  const [book, setBook] = useState<DayBookOut | null>(null);
  const [gst, setGst] = useState<GstSummaryOut | null>(null);
  const [ledgers, setLedgers] = useState<TallyLedgers | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [open, setOpen] = useState<string | null>(null); // the voucher whose lines are shown

  // Clear messages and collapse expanded rows when switching tabs, so stale feedback is not shown.
  function switchTab(next: Tab) {
    if (next !== tab) { setNotice(''); setError(''); }
    setTab(next);
  }

  const filter = { store_id: storeId, date_from: dateFrom, date_to: dateTo };

  // Reload Day Book + GST when the date, store, or active tab changes.
  // setOpen(null) collapses any expanded voucher row so old lines don't appear under new data.
  useEffect(() => {
    if (!dateFrom || !dateTo || tab === 'ledgers') return;
    let cancelled = false;
    setLoading(true);
    setError('');
    setOpen(null);
    Promise.all([getDayBook(filter), getGstSummary(filter)])
      .then(([b, g]) => { if (!cancelled) { setBook(b); setGst(g); } })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [storeId, dateFrom, dateTo, tab]);

  useEffect(() => {
    if (tab === 'ledgers' && !ledgers) getLedgers().then(setLedgers).catch((err) => setError(getErrorMessage(err)));
  }, [tab]);

  async function download(what: 'vouchers' | 'ledgers') {
    setBusy(true);
    setError('');
    try {
      await downloadTallyXml(filter, what);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitLedgers(e: FormEvent) {
    e.preventDefault();
    if (!ledgers) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      setLedgers(await saveLedgers(ledgers));
      setNotice(t('accounting.saved'));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const noStore = storeId === null;

  return (
    <div className="admin-page">
      <AdminNav />
      <div className="admin-header">
        <h2>{t('accounting.title')}</h2>
        {tab !== 'ledgers' && (
          <div className="admin-actions">
            <button className="btn-secondary" onClick={() => download('ledgers')} disabled={busy || !book?.vouchers.length}
              title={t('accounting.ledgersFileHint')}>
              {t('accounting.downloadLedgers')}
            </button>
            <button className="btn-primary" onClick={() => download('vouchers')} disabled={busy || !book?.vouchers.length}>
              {t('accounting.downloadVouchers')}
            </button>
          </div>
        )}
      </div>

      {tab !== 'ledgers' && (
        <div className="filter-bar">
          <input className="field-input filter-input" type="date" value={dateFrom} max={dateTo || isoDateIst()} onChange={(e) => setDateFrom(e.target.value)} />
          <span className="filter-sep">{t('reports.to')}</span>
          <input className="field-input filter-input" type="date" value={dateTo} min={dateFrom} max={isoDateIst()} onChange={(e) => setDateTo(e.target.value)} />
          {QUICK_RANGES.map((r) => (
            <button key={r.label} className="btn-sm" onClick={() => { const [f, to] = r.range(); setDateFrom(f); setDateTo(to); }}>{t(r.label)}</button>
          ))}
        </div>
      )}

      <div className="tab-bar" role="tablist">
        {(['daybook', 'gst', 'ledgers'] as Tab[]).map((key) => (
          <button key={key} role="tab" aria-selected={tab === key} className={`tab${tab === key ? ' active' : ''}`} onClick={() => switchTab(key)}>
            {t(`accounting.tabs.${key}`)}
          </button>
        ))}
      </div>

      {error && <div className="page-error">{error}</div>}
      {notice && <div className="page-error" style={{ background: 'var(--ok-bg)', color: 'var(--ok-text)', borderColor: 'var(--ok-text)' }}>{notice}</div>}
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      {tab === 'daybook' && book && (
        <>
          <p className="hint-text">{t(noStore ? 'accounting.daybookHintAll' : 'accounting.daybookHint')}</p>
          {book.warnings.length > 0 && (
            <div className="page-error" style={{ background: 'var(--warn-bg)', color: 'var(--warn-text)', borderColor: 'var(--warn-text)', display: 'block' }}>
              <strong>{t('accounting.warningsTitle')}</strong>
              <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{book.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            </div>
          )}
          <div className="stat-grid">
            {(['sales', 'credit_note', 'receipt', 'purchase', 'debit_note', 'payment'] as VoucherType[]).map((k) => (
              <div key={k} className="stat-tile">
                <span className="stat-label">{t(`accounting.types.${k}`)}</span>
                <span className="stat-value">{book.counts[k] ?? 0}</span>
              </div>
            ))}
          </div>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('accounting.colDate')}</th><th>{t('accounting.colType')}</th><th>{t('accounting.colNumber')}</th>
                  <th>{t('accounting.colParty')}</th><th>{t('accounting.colNarration')}</th><th className="num">{t('accounting.colAmount')}</th>
                </tr>
              </thead>
              <tbody>
                {book.vouchers.length === 0 && <tr><td colSpan={6} className="empty-row">{t('accounting.nothing')}</td></tr>}
                {book.vouchers.map((v) => (
                  <Fragment key={v.guid}>
                    <tr onClick={() => setOpen(open === v.guid ? null : v.guid)} style={{ cursor: 'pointer' }}
                      title={t('accounting.clickForLines')}>
                      <td style={{ whiteSpace: 'nowrap' }}>{v.date}</td>
                      <td>{t(`accounting.types.${v.voucher_type}`)}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.85em' }}>{v.number}{v.reference ? ` · ${v.reference}` : ''}</td>
                      <td>{v.party}</td>
                      <td style={{ fontSize: '0.9em' }}>{v.narration}</td>
                      <td className="num" style={{ fontWeight: 600 }}>{formatRupees(v.total_amount)}</td>
                    </tr>
                    {open === v.guid && (
                      <tr>
                        <td colSpan={6} style={{ background: 'var(--surface-2, #f8fafc)' }}>
                          <table className="data-table" style={{ margin: 0 }}>
                            <thead><tr><th>{t('accounting.colLedger')}</th><th className="num">{t('accounting.colDebit')}</th><th className="num">{t('accounting.colCredit')}</th></tr></thead>
                            <tbody>
                              {v.lines.map((ln) => (
                                <tr key={ln.ledger}><td>{ln.ledger}</td><td className="num">{amt(ln.debit)}</td><td className="num">{amt(ln.credit)}</td></tr>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint-text">{t('accounting.importHint')}</p>
        </>
      )}

      {tab === 'gst' && gst && (
        <>
          <p className="hint-text">{t('accounting.gstHint')}</p>
          {gst.warnings.length > 0 && (
            <div className="page-error" style={{ background: 'var(--warn-bg)', color: 'var(--warn-text)', borderColor: 'var(--warn-text)', display: 'block' }}>
              <ul style={{ margin: 0, paddingLeft: 18 }}>{gst.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            </div>
          )}
          <div className="stat-grid">
            <div className="stat-tile"><span className="stat-label">{t('accounting.outputGst')}</span>
              <span className="stat-value">{formatRupees(Number(gst.output_total.cgst) + Number(gst.output_total.sgst) + Number(gst.output_total.igst))}</span></div>
            <div className="stat-tile"><span className="stat-label">{t('accounting.inputGst')}</span>
              <span className="stat-value">{formatRupees(Number(gst.input_total.cgst) + Number(gst.input_total.sgst) + Number(gst.input_total.igst))}</span></div>
            <div className="stat-tile">
              <span className="stat-label">{t(Number(gst.net_payable) >= 0 ? 'accounting.netPayable' : 'accounting.netCredit')}</span>
              <span className="stat-value">{formatRupees(Math.abs(Number(gst.net_payable)))}</span>
              <span className="stat-sub">CGST {formatRupees(gst.net_cgst)} · SGST {formatRupees(gst.net_sgst)} · IGST {formatRupees(gst.net_igst)}</span>
            </div>
          </div>
          <div className="dash-columns">
            <section>
              <h3 className="section-title">{t('accounting.outputTitle')}</h3>
              <GstTable rows={gst.output} total={gst.output_total} showIgst={false} />
            </section>
            <section>
              <h3 className="section-title">{t('accounting.inputTitle')}</h3>
              <GstTable rows={gst.input} total={gst.input_total} showIgst />
            </section>
          </div>
        </>
      )}

      {tab === 'ledgers' && ledgers && (
        <form onSubmit={submitLedgers} className="modal-form" style={{ maxWidth: 720 }}>
          <p className="hint-text">{t('accounting.ledgersHint')}</p>
          {LEDGER_FIELDS.map((key) => (
            <label key={key} className="field-label">
              {t(`accounting.ledger.${key}`)}
              <input
                className="field-input"
                value={ledgers[key]}
                onChange={(e) => setLedgers({ ...ledgers, [key]: e.target.value })}
                maxLength={100}
                required
                disabled={!isAdmin}
              />
            </label>
          ))}
          {isAdmin ? (
            <div className="modal-buttons">
              <button type="submit" className="btn-primary" disabled={busy}>{busy ? t('common.saving') : t('common.save')}</button>
            </div>
          ) : (
            <p className="hint-text">{t('accounting.adminOnly')}</p>
          )}
        </form>
      )}
    </div>
  );
}
