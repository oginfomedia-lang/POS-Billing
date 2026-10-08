// This counter PC's receipt printer + cash drawer. Saved in counter.json on this PC (not on the server),
// so each counter can have its own printer. Only shown inside the Electron app.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { openDrawer, printReceipt } from '../../services/hardware/printerService';
import { useCounterStore } from '../../store/counterStore';
import { IconPrinter } from '../common/Icons';

interface PrinterItem {
  name: string;
  displayName: string;
}

export function PrinterSettingsCard() {
  const { t } = useTranslation();
  const { config, savePrinterSettings } = useCounterStore();
  const [printers, setPrinters] = useState<PrinterItem[]>([]);
  const [printerName, setPrinterName] = useState(config?.printerName ?? '');
  const [autoPrint, setAutoPrint] = useState(config?.autoPrint ?? true);
  const [drawerEnabled, setDrawerEnabled] = useState(config?.drawerEnabled ?? true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    window.posBridge.listPrinters().then(setPrinters).catch(() => setPrinters([]));
  }, []);

  useEffect(() => {
    if (!config) return;
    setPrinterName(config.printerName);
    setAutoPrint(config.autoPrint);
    setDrawerEnabled(config.drawerEnabled);
  }, [config]);

  const dirty =
    config !== null &&
    (printerName !== config.printerName || autoPrint !== config.autoPrint || drawerEnabled !== config.drawerEnabled);

  async function run(action: () => Promise<{ ok: boolean; error?: string }>, success: string) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await action();
      setMessage(result.ok ? { ok: true, text: success } : { ok: false, text: result.error || t('printer.failed') });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  }

  /** Prints a small sample slip (not the Settings page): print CSS shows only .print-test-receipt. */
  async function testPrint() {
    document.body.classList.add('printing-test');
    try {
      return await printReceipt();
    } finally {
      document.body.classList.remove('printing-test');
    }
  }

  function save() {
    return run(async () => {
      await savePrinterSettings({ printerName, autoPrint, drawerEnabled });
      return { ok: true };
    }, t('printer.saved'));
  }

  return (
    <section className="modal-form settings-form printer-card">
      <div className="title-with-icon">
        <IconPrinter size={18} />
        <h3>{t('printer.title')}</h3>
      </div>
      <p className="hint-text">{t('printer.hint')}</p>
      {message && <div className={message.ok ? 'notice-bar' : 'form-error'}>{message.text}</div>}

      <label className="field-label">
        {t('printer.printer')}
        <select className="field-input" value={printerName} disabled={busy} onChange={(e) => setPrinterName(e.target.value)}>
          <option value="">{t('printer.windowsDefault')}</option>
          {printers.map((p) => <option key={p.name} value={p.name}>{p.displayName}</option>)}
          {printerName && !printers.some((p) => p.name === printerName) && (
            <option value={printerName}>{t('printer.notFound', { name: printerName })}</option>
          )}
        </select>
      </label>
      <label className="field-label checkbox-label">
        <input type="checkbox" checked={autoPrint} disabled={busy} onChange={(e) => setAutoPrint(e.target.checked)} />
        {t('printer.autoPrint')}
      </label>
      <label className="field-label checkbox-label">
        <input type="checkbox" checked={drawerEnabled} disabled={busy} onChange={(e) => setDrawerEnabled(e.target.checked)} />
        {t('printer.drawer')}
      </label>

      <div className="modal-buttons">
        <button type="button" className="btn-secondary" disabled={busy || dirty} title={dirty ? t('printer.saveFirst') : undefined}
          onClick={() => run(testPrint, t('printer.testSent'))}>
          {t('printer.testPrint')}
        </button>
        <button type="button" className="btn-secondary" disabled={busy || dirty || !drawerEnabled} title={dirty ? t('printer.saveFirst') : undefined}
          onClick={() => run(openDrawer, t('printer.drawerSent'))}>
          {t('printer.openDrawer')}
        </button>
        <button type="button" className="btn-primary" disabled={busy || !dirty} onClick={save}>
          {busy ? t('common.saving') : t('printer.save')}
        </button>
      </div>

      <article className="receipt print-test-receipt" aria-hidden="true">
        <div className="receipt-center"><strong className="receipt-store">{t('printer.testTitle')}</strong></div>
        <hr />
        <div className="receipt-row"><span>{t('printer.printer')}</span><span>{config?.printerName || t('printer.windowsDefault')}</span></div>
        <div className="receipt-row"><span>{t('receipt.counter', { code: config?.counterCode ?? '' })}</span><span>{new Date().toLocaleString()}</span></div>
        <hr />
        <div className="receipt-center">{t('printer.testLine')}</div>
        <div className="receipt-center">अ आ इ ई — ₹ 123.45</div>
      </article>
    </section>
  );
}
