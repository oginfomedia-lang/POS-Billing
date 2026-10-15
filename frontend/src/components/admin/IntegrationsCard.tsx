// Razorpay / Paytm / WhatsApp details entered by the admin instead of the server's .env file.
// Secrets are never sent back: a saved one shows as "saved", typing replaces it, "Remove" deletes it.
import type { ParseKeys } from 'i18next';
import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getErrorMessage } from '../../services/api/httpClient';
import { getIntegrations, saveIntegrations, testIntegration } from '../../services/api/integrationApi';
import type { IntegrationProvider, IntegrationsUpdate, IntegrationsView, PlainField, SecretField } from '../../types/integrations';

type Kind = 'text' | 'secret' | 'bool' | 'int';

const SECTIONS: { provider: IntegrationProvider; fields: [string, Kind][]; testable: boolean }[] = [
  {
    provider: 'razorpay',
    testable: true,
    fields: [
      ['RAZORPAY_KEY_ID', 'text'], ['RAZORPAY_KEY_SECRET', 'secret'], ['RAZORPAY_POS_BASE_URL', 'text'],
      ['RAZORPAY_POS_USERNAME', 'text'], ['RAZORPAY_POS_APP_KEY', 'secret'], ['UPI_QR_EXPIRY_SECONDS', 'int'],
      ['RAZORPAY_MOCK', 'bool'],
    ],
  },
  {
    provider: 'paytm',
    testable: false,
    fields: [
      ['PAYTM_MID', 'text'], ['PAYTM_CLIENT_ID', 'text'], ['PAYTM_MERCHANT_KEY', 'secret'], ['PAYTM_BASE_URL', 'text'],
      ['PAYTM_MOCK', 'bool'],
    ],
  },
  {
    provider: 'whatsapp',
    testable: true,
    fields: [
      ['WHATSAPP_TOKEN', 'secret'], ['WHATSAPP_PHONE_NUMBER_ID', 'text'], ['WHATSAPP_TEMPLATE_NAME', 'text'],
      ['WHATSAPP_EBILL_TEMPLATE_NAME', 'text'], ['WHATSAPP_TEMPLATE_LANG', 'text'], ['WHATSAPP_MOCK', 'bool'],
    ],
  },
];

/** What the box shows for a saved plain field ('' when nothing is set anywhere). */
function shown(field: PlainField | undefined): string | boolean {
  if (!field || field.value === null) return '';
  return typeof field.value === 'boolean' ? field.value : String(field.value);
}

export function IntegrationsCard() {
  const { t } = useTranslation();
  const [view, setView] = useState<IntegrationsView | null>(null);
  // Edits not saved yet: plain fields hold the new box value; secrets hold newly typed text.
  const [drafts, setDrafts] = useState<Record<string, string | boolean>>({});
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<IntegrationProvider | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    getIntegrations().then(setView).catch((err) => setMessage({ ok: false, text: getErrorMessage(err) }));
  }, []);

  const dirty = Object.keys(drafts).length > 0 || removed.size > 0;

  function edit(name: string, value: string | boolean) {
    setDrafts((d) => ({ ...d, [name]: value }));
    setMessage(null);
  }

  function remove(name: string) {
    setRemoved((r) => new Set(r).add(name));
    setDrafts((d) => { const next = { ...d }; delete next[name]; return next; });
    setMessage(null);
  }

  /** Only what changed: typed secrets, removed secrets, and plain fields that differ from what's saved. */
  function payload(): IntegrationsUpdate {
    if (!view) return {};
    const out: IntegrationsUpdate = {};
    for (const { provider, fields } of SECTIONS) {
      for (const [name, kind] of fields) {
        const draft = drafts[name];
        if (kind === 'secret') {
          if (typeof draft === 'string' && draft.trim()) out[name] = draft.trim();
          else if (removed.has(name)) out[name] = '';
          continue;
        }
        if (draft === undefined || draft === shown(view[provider][name] as PlainField)) continue;
        out[name] = kind === 'int' && draft !== '' ? Number(draft) : typeof draft === 'string' ? draft.trim() : draft;
      }
    }
    return out;
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      setView(await saveIntegrations(payload()));
      setDrafts({});
      setRemoved(new Set());
      setMessage({ ok: true, text: t('settings.integrations.saved') });
    } catch (err) {
      setMessage({ ok: false, text: getErrorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  async function test(provider: 'razorpay' | 'whatsapp') {
    setTesting(provider);
    setMessage(null);
    try {
      setMessage({ ok: true, text: await testIntegration(provider) });
    } catch (err) {
      setMessage({ ok: false, text: getErrorMessage(err) });
    } finally {
      setTesting(null);
    }
  }

  return (
    <form className="modal-form settings-form integrations-card" onSubmit={save}>
      <h3>{t('settings.integrations.title')}</h3>
      <p className="hint-text">{t('settings.integrations.hint')}</p>
      {message && <div className={message.ok ? 'notice-bar' : 'form-error'}>{message.text}</div>}
      {!view && !message && <div className="loading-text">{t('common.loading')}</div>}

      {view && SECTIONS.map(({ provider, fields, testable }) => (
        <section key={provider} className="integration-section">
          <h4 className="section-title">
            {t(`settings.integrations.sections.${provider}`)}
            {provider === 'paytm' && <span className="badge-warning integration-badge">{t('settings.integrations.paytmNotActive')}</span>}
          </h4>
          {fields.map(([name, kind]) => {
            const label = t(`settings.integrations.fields.${name}` as ParseKeys);
            if (kind === 'bool') {
              const value = drafts[name] ?? shown(view[provider][name] as PlainField);
              return (
                <label key={name} className="field-label checkbox-label">
                  <input type="checkbox" checked={value === true} disabled={saving} onChange={(e) => edit(name, e.target.checked)} />
                  {label}
                </label>
              );
            }
            if (kind === 'secret') {
              const field = view[provider][name] as SecretField;
              const isRemoved = removed.has(name);
              const placeholder = isRemoved
                ? t('settings.integrations.willRemove')
                : field.set ? t(field.from_env ? 'settings.integrations.secretFromEnv' : 'settings.integrations.secretSaved')
                  : t('settings.integrations.secretNotSet');
              return (
                <label key={name} className="field-label">
                  {label}
                  <input
                    className="field-input"
                    type="password"
                    autoComplete="new-password"
                    value={(drafts[name] as string | undefined) ?? ''}
                    placeholder={placeholder}
                    disabled={saving}
                    onChange={(e) => edit(name, e.target.value)}
                  />
                  {field.unreadable && <span className="hint-text text-danger">{t('settings.integrations.unreadable')}</span>}
                  {(field.set || field.unreadable) && !field.from_env && !isRemoved && (
                    <button type="button" className="link-button integration-remove" onClick={() => remove(name)}>
                      {t('settings.integrations.remove')}
                    </button>
                  )}
                </label>
              );
            }
            const field = view[provider][name] as PlainField;
            const value = drafts[name] ?? shown(field);
            return (
              <label key={name} className="field-label">
                {label}
                <input
                  className="field-input"
                  type={kind === 'int' ? 'number' : 'text'}
                  value={value as string}
                  disabled={saving}
                  onChange={(e) => edit(name, e.target.value)}
                />
                {field.from_env && field.value !== null && field.value !== '' && drafts[name] === undefined && (
                  <span className="hint-text">{t('settings.integrations.fromEnv')}</span>
                )}
              </label>
            );
          })}
          {testable && (
            <div className="integration-actions">
              <button
                type="button"
                className="btn-secondary"
                disabled={saving || testing !== null || dirty}
                title={dirty ? t('settings.integrations.saveFirst') : undefined}
                onClick={() => void test(provider as 'razorpay' | 'whatsapp')}
              >
                {testing === provider ? t('settings.integrations.testing') : t('settings.integrations.test')}
              </button>
              {dirty && <span className="hint-text">{t('settings.integrations.saveFirst')}</span>}
            </div>
          )}
        </section>
      ))}

      {view && (
        <div className="modal-buttons">
          <button className="btn-primary" type="submit" disabled={saving || !dirty}>
            {saving ? t('common.saving') : t('settings.integrations.save')}
          </button>
        </div>
      )}
    </form>
  );
}
