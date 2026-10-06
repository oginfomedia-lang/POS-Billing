// Shift API calls.
import axios from 'axios';
import type { ShiftOut } from '../../types/shift';
import { httpClient } from './httpClient';

/** Returns null when the user has no open shift. */
export async function getActiveShift(): Promise<ShiftOut | null> {
  try {
    const resp = await httpClient.get<ShiftOut>('/shifts/active');
    return resp.data;
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.status === 404) return null;
    throw err;
  }
}

export async function openShift(counterCode: string, openingCash: string): Promise<ShiftOut> {
  const resp = await httpClient.post<ShiftOut>('/shifts/open', {
    counter_code: counterCode,
    opening_cash: openingCash,
  });
  return resp.data;
}
