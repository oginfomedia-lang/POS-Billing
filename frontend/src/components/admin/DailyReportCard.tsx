// Nightly WhatsApp collection summary: on/off, send time and owner mobiles (saved with the other
// settings), a "send now" button, and the last messages with their status.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getErrorMessage } from '../../services/api/httpClient';
import { getDailyReportLogs, sendDailyReportNow } from '../../services/api/reportApi';
import type { DailyReportLog, SettingsData } from '../../types/report';
import { formatDateTime } from '../../utils/format';

type ReportFields = Pick<SettingsData, 'daily_report_enabled' | 'daily_report_time' | 'daily_report_mobiles'>;

interface Props {
  value: ReportFields;
  onChange: <K extends keyof SettingsData>(key: K, value: SettingsData[K]) => void;
  /** Unsaved changes in these fields: "send now" would use the old numbers. */
  dirty: boolean;
  /** Saves all settings (these fields included). */
  onSave: () => void;
  canEdit: boolean;
  disabled: boolean;
}

const STATUS_CLASS: Record<DailyReportLog['status'], string> = { sent: 'stock-in', pending: 'stock-low', failed: 'stock-out' };

export function DailyReportCard({ value, onChange, dirty, onSave, canEdit, disabled }: Props) {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<DailyReportLog[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  function loadLogs() {
    getDailyReportLogs().then(setLogs).catch(() => setLogs([]));
  }

  useEffect(loadLogs, []);

  async function sendNow() {
    setBusy(true);
    setMessage(null);
    try {
      const results = await sendDailyReportNow();
      const sent = results.filter((r) => r.status === 'sent').length;
      const failed = results.find((r) => r.error);
      setMessage({
        ok: sent === results.length,
        text: t('settings.dailyReport.sendResult', { sent, total: results.length }) + (failed ? ` ${failed.error}` : ''),
      });
    } catch (err) {
      setMessage({ ok: false, text: getErrorMessage(err) });
    } finally {
      setBusy(false);
      loadLogs();
    }
  }

  const noMobiles = !value.daily_report_mobiles.trim();

  return (
    <form className="modal-form settings-form daily-report-card" onSubmit={(e) => { e.preventDefault(); onSave(); }}>
      <h3>{t('settings.dailyReport.title')}</h3>
      <p className="hint-text">{t('settings.dailyReport.hint')}</p>
      {message && <div className={message.ok ? 'notice-bar' : 'form-error'}>{message.text}</div>}

      <label className="field-label checkbox-label">
        <input
          type="checkbox"
          checked={value.daily_report_enabled}
          disabled={!canEdit || disabled}
          onChange={(e) => onChange('daily_report_enabled', e.target.checked)}
        />
        {t('settings.dailyReport.enabled')}
      </label>
      <label className="field-label">
        {t('settings.dailyReport.time')}
        <input
          className="field-input"
          type="time"
          value={value.daily_report_time}
          disabled={!canEdit || disabled}
          onChange={(e) => onChange('daily_report_time', e.target.value)}
          required
        />
      </label>
      <label className="field-label">
        {t('settings.dailyReport.mobiles')}
        <input
          className="field-input"
          inputMode="tel"
          maxLength={200}
          value={value.daily_report_mobiles}
          disabled={!canEdit || disabled}
          placeholder={t('settings.dailyReport.mobilesPlaceholder')}
          onChange={(e) => onChange('daily_report_mobiles', e.target.value)}
        />
        <span className="hint-text">{t('settings.dailyReport.mobilesHint')}</span>
      </label>

      {canEdit && (
        <div className="modal-buttons">
          <button
            type="button"
            className="btn-secondary"
            disabled={busy || disabled || dirty || noMobiles}
            title={dirty ? t('settings.dailyReport.saveFirst') : undefined}
            onClick={sendNow}
          >
            {busy ? t('settings.dailyReport.sending') : t('settings.dailyReport.sendNow')}
          </button>
          <button type="submit" className="btn-primary" disabled={busy || disabled || !dirty}>
            {disabled ? t('common.saving') : t('settings.saveBtn')}
          </button>
        </div>
      )}

      <h4 className="section-title">{t('settings.dailyReport.logTitle')}</h4>
      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('settings.dailyReport.colDate')}</th>
              <th>{t('common.store')}</th>
              <th>{t('settings.dailyReport.colTo')}</th>
              <th>{t('settings.dailyReport.colStatus')}</th>
              <th className="num">{t('settings.dailyReport.colTries')}</th>
              <th>{t('settings.dailyReport.colUpdated')}</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 && <tr><td colSpan={6} className="empty-row">{t('settings.dailyReport.noLogs')}</td></tr>}
            {logs.map((log) => (
              <tr key={log.id} title={log.body ?? undefined}>
                <td>
                  {log.report_date}
                  {log.kind === 'daily_collection_manual' && <span className="status-muted"> ({t('settings.dailyReport.manual')})</span>}
                </td>
                <td>{log.store_name}</td>
                <td>{log.recipient}</td>
                <td>
                  <span className={`stock-badge ${STATUS_CLASS[log.status]}`}>{t(`settings.dailyReport.status.${log.status}`)}</span>
                  {log.error && <div className="status-muted">{log.error}</div>}
                </td>
                <td className="num">{log.attempts}</td>
                <td className="ts-cell">{formatDateTime(log.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </form>
  );
}
