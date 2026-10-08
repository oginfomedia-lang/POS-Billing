// Store and counter API calls.
import type { CounterOut, PagedResponse, StoreOut } from '../../types/api';
import { httpClient } from './httpClient';

export interface StoreInput {
  name: string;
  address?: string | null;
  phone?: string | null;
  gstin?: string | null;
}

export async function listStores(): Promise<StoreOut[]> {
  const resp = await httpClient.get<PagedResponse<StoreOut>>('/stores', { params: { per_page: 100 } });
  return resp.data.items;
}

export async function createStore(data: StoreInput): Promise<StoreOut> {
  const resp = await httpClient.post<StoreOut>('/stores', data);
  return resp.data;
}

export async function updateStore(id: number, data: Partial<StoreInput> & { is_active?: boolean }): Promise<StoreOut> {
  const resp = await httpClient.put<StoreOut>(`/stores/${id}`, data);
  return resp.data;
}

export async function listCounters(storeId: number): Promise<CounterOut[]> {
  const resp = await httpClient.get<CounterOut[]>(`/stores/${storeId}/counters`);
  return resp.data;
}

export async function createCounter(
  storeId: number,
  code: string,
  label: string,
  edcDeviceId?: string | null,
): Promise<CounterOut> {
  const resp = await httpClient.post<CounterOut>(`/stores/${storeId}/counters`, {
    code,
    label,
    edc_device_id: edcDeviceId || null,
  });
  return resp.data;
}

export async function updateCounter(
  storeId: number,
  counterId: number,
  data: { label?: string; is_active?: boolean; edc_device_id?: string }, // edc_device_id "" removes the machine
): Promise<CounterOut> {
  const resp = await httpClient.put<CounterOut>(`/stores/${storeId}/counters/${counterId}`, data);
  return resp.data;
}
