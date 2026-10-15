// Settings → Integrations: Razorpay / Paytm / WhatsApp details (admin only). Secrets are never returned.
import type { IntegrationProvider, IntegrationsUpdate, IntegrationsView } from '../../types/integrations';
import { httpClient } from './httpClient';

export async function getIntegrations(): Promise<IntegrationsView> {
  const resp = await httpClient.get<IntegrationsView>('/settings/integrations');
  return resp.data;
}

/** Only the fields sent change: "" removes a saved value (back to the server .env). */
export async function saveIntegrations(data: IntegrationsUpdate): Promise<IntegrationsView> {
  const resp = await httpClient.put<IntegrationsView>('/settings/integrations', data);
  return resp.data;
}

/** Checks the saved credentials with a read-only call. Returns the server's message. */
export async function testIntegration(provider: Exclude<IntegrationProvider, 'paytm'>): Promise<string> {
  const resp = await httpClient.post<{ message: string }>(`/settings/integrations/test/${provider}`);
  return resp.data.message;
}
