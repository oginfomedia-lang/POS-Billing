// Receipt text, store-wide inventory defaults, return window, WhatsApp daily report, and this counter's printer.
import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AdminNav } from '../../components/admin/AdminNav';
import { DailyReportCard } from '../../components/admin/DailyReportCard';
import { PrinterSettingsCard } from '../../components/admin/PrinterSettingsCard';
import { useAuth } from '../../hooks/useAuth';
import { getErrorMessage } from '../../services/api/httpClient';
import { getSettings, saveSettings } from '../../services/api/reportApi';
import { hasPrinterBridge } from '../../services/hardware/printerService';
import type { SettingsData } from '../../types/report';

const DEFAULTS: SettingsData = {
  receipt_header: '',
  receipt_footer: 'Thank you! Visit again.',
  low_stock_threshold: '5',
  return_window_days: 30,
  rewards_enabled: false,
  reward_rupees_per_point: '100',
  reward_block_points: 100,
  reward_block_value: '100',
  daily_report_enabled: false,
  daily_report_time: '22:30',
  daily_report_mobiles: '',
};

export function SettingsPage() {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();
  const [settings, setSettings] = useState<SettingsData>(DEFAULTS);
  const [savedSettings, setSavedSettings] = useState<SettingsData>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((data) => { if (!cancelled) { setSettings(data); setSavedSettings(data); } })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const saved = await saveSettings(settings);
      setSettings(saved);
      setSavedSettings(saved);
      setNotice(t('settings.saved'));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function update<K extends keyof SettingsData>(key: K, value: SettingsData[K]) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="admin-page settings-page">
      <AdminNav />
      <div className="admin-header"><h2>{t('settings.title')}</h2></div>
      {error && <div className="page-error">{error}</div>}
      {notice && <div className="notice-bar">{notice}</div>}
      {loading ? (
        <div className="loading-text">{t('settings.loading')}</div>
      ) : (
        <form className="modal-form settings-form" onSubmit={submit}>
          <p className="hint-text">
            {t('settings.hint')}
          </p>
          <label className="field-label">
            {t('settings.header')}
            <input
              className="field-input"
              maxLength={200}
              value={settings.receipt_header}
              disabled={!isAdmin || saving}
              onChange={(e) => update('receipt_header', e.target.value)}
              placeholder={t('settings.headerPlaceholder')}
            />
          </label>
          <label className="field-label">
            {t('settings.footer')}
            <input
              className="field-input"
              maxLength={200}
              value={settings.receipt_footer}
              disabled={!isAdmin || saving}
              onChange={(e) => update('receipt_footer', e.target.value)}
            />
          </label>
          <label className="field-label">
            {t('settings.threshold')}
            <input
              className="field-input"
              type="number"
              min="0"
              max="999999999"
              step="0.001"
              value={settings.low_stock_threshold}
              disabled={!isAdmin || saving}
              onChange={(e) => update('low_stock_threshold', e.target.value)}
              required
            />
          </label>
          <label className="field-label">
            {t('settings.returnWindowDays')}
            <input
              className="field-input"
              type="number"
              min="0"
              max="365"
              step="1"
              value={settings.return_window_days}
              disabled={!isAdmin || saving}
              onChange={(e) => update('return_window_days', Number(e.target.value))}
              required
            />
            <span className="hint-text">{t('settings.returnWindowHint')}</span>
          </label>
          <h3 className="section-title">{t('settings.rewards.title')}</h3>
          <label className="field-label checkbox-label">
            <input
              type="checkbox"
              checked={settings.rewards_enabled}
              disabled={!isAdmin || saving}
              onChange={(e) => update('rewards_enabled', e.target.checked)}
            />
            {t('settings.rewards.enabled')}
          </label>
          <label className="field-label">
            {t('settings.rewards.rupeesPerPoint')}
            <input
              className="field-input"
              type="number"
              min="1"
              step="1"
              value={settings.reward_rupees_per_point}
              disabled={!isAdmin || saving}
              onChange={(e) => update('reward_rupees_per_point', e.target.value)}
              required
            />
          </label>
          <label className="field-label">
            {t('settings.rewards.blockPoints')}
            <input
              className="field-input"
              type="number"
              min="1"
              step="1"
              value={settings.reward_block_points}
              disabled={!isAdmin || saving}
              onChange={(e) => update('reward_block_points', Number(e.target.value))}
              required
            />
          </label>
          <label className="field-label">
            {t('settings.rewards.blockValue')}
            <input
              className="field-input"
              type="number"
              min="1"
              step="1"
              value={settings.reward_block_value}
              disabled={!isAdmin || saving}
              onChange={(e) => update('reward_block_value', e.target.value)}
              required
            />
            <span className="hint-text">{t('settings.rewards.hint')}</span>
          </label>
          {isAdmin ? (
            <div className="modal-buttons">
              <button className="btn-primary" type="submit" disabled={saving}>
                {saving ? t('common.saving') : t('settings.saveBtn')}
              </button>
            </div>
          ) : (
            <p className="hint-text">{t('settings.adminOnly')}</p>
          )}
        </form>
      )}
      {!loading && (
        <DailyReportCard
          value={settings}
          onChange={update}
          dirty={(['daily_report_enabled', 'daily_report_time', 'daily_report_mobiles'] as const).some((k) => settings[k] !== savedSettings[k])}
          onSave={() => void submit()}
          canEdit={isAdmin}
          disabled={saving}
        />
      )}
      {hasPrinterBridge() && <PrinterSettingsCard />}
    </div>
  );
}
