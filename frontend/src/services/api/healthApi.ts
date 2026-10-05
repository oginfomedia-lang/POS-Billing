// Server health check API call.
import type { HealthResponse } from '../../types/api';
import { httpClient } from './httpClient';

export async function getHealth(): Promise<HealthResponse> {
  // 503 still has a useful body (database down), so do not treat it as a failure.
  const response = await httpClient.get<HealthResponse>('/health', {
    timeout: 5_000,
    validateStatus: (status) => status === 200 || status === 503,
  });
  return response.data;
}
