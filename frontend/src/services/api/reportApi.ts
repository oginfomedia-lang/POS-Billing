// Report, discount and settings API calls (admin / manager screens).
import type {
  CollectionReportOut, DailyReportLog, DailyReportSendResult, DashboardOut, DiscountIn, DiscountOut, ProfitReportOut, SalesReportOut, SettingsData, ShiftRow,
} from '../../types/report';
import { httpClient } from './httpClient';

export interface ReportFilter {
  store_id?: number | null;
  /** Inclusive dates, YYYY-MM-DD (IST business dates). */
  date_from: string;
  date_to: string;
}

function params(f: ReportFilter) {
  return { store_id: f.store_id ?? undefined, date_from: f.date_from, date_to: f.date_to };
}

export async function getDashboard(storeId?: number | null): Promise<DashboardOut> {
  const resp = await httpClient.get<DashboardOut>('/reports/dashboard', { params: { store_id: storeId ?? undefined } });
  return resp.data;
}

export async function getSalesReport(f: ReportFilter): Promise<SalesReportOut> {
  const resp = await httpClient.get<SalesReportOut>('/reports/sales', { params: params(f) });
  return resp.data;
}

/** Admin only (403 for others). */
export async function getProfitReport(f: ReportFilter): Promise<ProfitReportOut> {
  const resp = await httpClient.get<ProfitReportOut>('/reports/profit', { params: params(f) });
  return resp.data;
}

export async function getShiftReport(f: ReportFilter): Promise<ShiftRow[]> {
  const resp = await httpClient.get<ShiftRow[]>('/reports/shifts', { params: params(f) });
  return resp.data;
}

export async function getCollectionReport(f: ReportFilter): Promise<CollectionReportOut> {
  const resp = await httpClient.get<CollectionReportOut>('/reports/collection', { params: params(f) });
  return resp.data;
}

/** storeId: that branch's offers plus all-branch offers; omit for every offer (head office). */
export async function listDiscounts(storeId?: number | null): Promise<DiscountOut[]> {
  const resp = await httpClient.get<DiscountOut[]>('/discounts', { params: { store_id: storeId ?? undefined } });
  return resp.data;
}

export async function saveDiscount(id: number | null, data: DiscountIn): Promise<DiscountOut> {
  const resp = id === null
    ? await httpClient.post<DiscountOut>('/discounts', data)
    : await httpClient.put<DiscountOut>(`/discounts/${id}`, data);
  return resp.data;
}

export async function getSettings(): Promise<SettingsData> {
  const resp = await httpClient.get<SettingsData>('/settings');
  return resp.data;
}

export async function saveSettings(data: SettingsData): Promise<SettingsData> {
  const resp = await httpClient.put<SettingsData>('/settings', data);
  return resp.data;
}

/** Sends today's collection summary on WhatsApp right now (admin). */
export async function sendDailyReportNow(): Promise<DailyReportSendResult[]> {
  const resp = await httpClient.post<DailyReportSendResult[]>('/settings/daily-report/send');
  return resp.data;
}

export async function getDailyReportLogs(): Promise<DailyReportLog[]> {
  const resp = await httpClient.get<DailyReportLog[]>('/settings/daily-report/logs');
  return resp.data;
}
