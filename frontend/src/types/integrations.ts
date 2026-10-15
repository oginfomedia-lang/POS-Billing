// Settings → Integrations (backend services/integration_settings_service.py).

export type IntegrationProvider = 'razorpay' | 'paytm' | 'whatsapp';

/** A normal field: its value, and whether it currently comes from the server's .env file. */
export interface PlainField {
  value: string | number | boolean | null;
  from_env: boolean;
}

/** A secret: never sent back, only whether one is set. unreadable = saved but can't be decrypted. */
export interface SecretField {
  set: boolean;
  unreadable: boolean;
  from_env: boolean;
}

export type IntegrationsView = Record<IntegrationProvider, Record<string, PlainField | SecretField>>;

/** null/missing = keep, "" = remove (back to .env), otherwise the new value. */
export type IntegrationsUpdate = Record<string, string | number | boolean | null>;
