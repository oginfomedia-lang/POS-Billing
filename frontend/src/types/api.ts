// Shared API response and error types.

/** Every backend error looks like this (see backend/app/errors/handlers.py). */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  database: 'up' | 'down';
  server_time: string;
}
