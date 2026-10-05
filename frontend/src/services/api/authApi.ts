// Login, refresh and current-user API calls.
import type { RefreshResponse, TokenResponse, UserOut } from '../../types/api';
import { httpClient } from './httpClient';

export async function login(username: string, pin: string): Promise<TokenResponse> {
  const resp = await httpClient.post<TokenResponse>('/auth/login', { username, pin });
  return resp.data;
}

/** Exchange a refresh token for a new access token. */
export async function refreshToken(token: string): Promise<RefreshResponse> {
  const resp = await httpClient.post<RefreshResponse>(
    '/auth/refresh',
    {},
    { headers: { Authorization: `Bearer ${token}` } },
  );
  return resp.data;
}

export async function getMe(token: string): Promise<UserOut> {
  const resp = await httpClient.get<UserOut>('/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  });
  return resp.data;
}
