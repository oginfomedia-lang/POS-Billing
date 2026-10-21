import type { CloseShiftRequest, OpenShiftRequest, ShiftBills, ShiftOut } from '../../types/shift';
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

/** Bills, refunds and expected cash for one shift (the cashier's own; admin / manager any in their store). */
export async function getShiftBills(shiftId: number): Promise<ShiftBills> {
  const resp = await httpClient.get<ShiftBills>(`/shifts/${shiftId}/bills`);
  return resp.data;
}
