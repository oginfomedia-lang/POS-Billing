// Accounting (Tally) API calls: ledger names, Day Book, GST summary, Tally import files.
import type { DayBookOut, GstSummaryOut, TallyLedgers } from '../../types/accounting';
import { httpClient } from './httpClient';
import type { ReportFilter } from './reportApi';

function params(f: ReportFilter) {
  return { store_id: f.store_id ?? undefined, date_from: f.date_from, date_to: f.date_to };
}

export async function getLedgers(): Promise<TallyLedgers> {
  return (await httpClient.get<TallyLedgers>('/accounting/ledgers')).data;
}

export async function saveLedgers(names: TallyLedgers): Promise<TallyLedgers> {
  return (await httpClient.put<TallyLedgers>('/accounting/ledgers', names)).data;
}

export async function getDayBook(f: ReportFilter): Promise<DayBookOut> {
  return (await httpClient.get<DayBookOut>('/accounting/daybook', { params: params(f) })).data;
}

export async function getGstSummary(f: ReportFilter): Promise<GstSummaryOut> {
  return (await httpClient.get<GstSummaryOut>('/accounting/gst-summary', { params: params(f) })).data;
}

/** Saves the Tally import file: the vouchers, or (once, before them) the ledgers they use. */
export async function downloadTallyXml(f: ReportFilter, what: 'vouchers' | 'ledgers'): Promise<void> {
  const resp = await httpClient.get<Blob>('/accounting/tally-export', {
    params: { ...params(f), what }, responseType: 'blob',
  });
  const range = f.date_from === f.date_to ? f.date_from : `${f.date_from}_to_${f.date_to}`;
  const url = URL.createObjectURL(resp.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = `tally-${what}-${range}.xml`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
