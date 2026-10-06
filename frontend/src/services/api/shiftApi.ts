import type { CloseShiftRequest, OpenShiftRequest, ShiftOut } from '../../types/shift';
import { httpClient } from './httpClient';

export async function openShift(data: OpenShiftRequest): Promise<ShiftOut> {
  const resp = await httpClient.post<ShiftOut>('/shifts/open', data);
  return resp.data;
}

export async function getActiveShift(): Promise<ShiftOut> {
  const resp = await httpClient.get<ShiftOut>('/shifts/active');
  return resp.data;
}

export async function closeShift(shiftId: number, data: CloseShiftRequest): Promise<ShiftOut> {
  const resp = await httpClient.post<ShiftOut>(`/shifts/${shiftId}/close`, data);
  return resp.data;
}
