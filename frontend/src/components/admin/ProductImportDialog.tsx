// Bulk product import from a CSV / Excel file: choose file → check every row (nothing saved) → import.
// Rows whose SKU or barcode already exists update that product; the import is all or nothing.
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getErrorMessage } from '../../services/api/httpClient';
import { downloadImportTemplate, previewImport, runImport } from '../../services/api/productApi';
import type { StoreOut } from '../../types/api';
import type { ImportOptions, ImportPreview, ImportResult } from '../../types/product';
import { IconX } from '../common/Icons';

/** Rendering thousands of rows makes the dialog sluggish; the counts above the table cover the rest. */
const MAX_SHOWN = 300;

interface Props {
  stores: StoreOut[];
  defaultStoreId: number | null;
  onImported: () => void;
  onClose: () => void;
}

export function ProductImportDialog({ stores, defaultStoreId, onImported, onClose }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<ImportOptions>({
    store_id: defaultStoreId ?? stores[0]?.id ?? null,
    sold_in: 'all',
    generate_barcodes: true,
  });
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [onlyProblems, setOnlyProblems] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useKeyboardShortcuts({ Escape: () => { if (!busy) onClose(); } });

  const shownRows = useMemo(() => {
    if (!preview) return [];
    const rows = onlyProblems ? preview.rows.filter((r) => r.errors.length || r.warnings.length) : preview.rows;
    return rows.slice(0, MAX_SHOWN);
  }, [preview, onlyProblems]);

  function changeOptions(next: Partial<ImportOptions>) {
    setOptions((o) => ({ ...o, ...next }));
    setPreview(null); // options change what a row means: check again
  }

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError('');
    try {
      return await fn();
    } catch (err) {
      setError(getErrorMessage(err));
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  async function check() {
    if (!file) return;
    const p = await run(() => previewImport(file, options));
    if (p) {
      setPreview(p);
      setOnlyProblems(p.errors > 0 || p.rows.some((r) => r.warnings.length > 0));
    }
  }

  async function doImport() {
    if (!file) return;
    const out = await run(() => runImport(file, options));
    if (!out) return;
    if ('preview' in out) {
      setPreview(out.preview); // someone changed products meanwhile: show the new problems
      setOnlyProblems(true);
      return;
    }
    setResult(out.result);
    onImported();
  }

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-wide import-dialog">
        <div className="modal-header">
          <div>
            <span className="modal-subtitle">{t('import.subtitle')}</span>
            <h3 className="modal-title">{t('import.title')}</h3>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose} disabled={busy}>
            <IconX size={18} />
          </button>
        </div>

        {error && <div className="form-error">{error}</div>}

        {result ? (
          <div className="modal-form">
            <div className="notice-bar">
              {t('import.done', { created: result.created, updated: result.updated, stock: result.opening_stock_rows })}
            </div>
            {result.new_categories.length > 0 && (
              <p className="hint-text">{t('import.newCategories', { names: result.new_categories.join(', ') })}</p>
            )}
            {result.generated_barcodes.length > 0 && (
              <>
                <h4 className="section-title">{t('import.generatedTitle', { count: result.generated_barcodes.length })}</h4>
                <div className="table-card import-table">
                  <table className="data-table">
                    <tbody>
                      {result.generated_barcodes.map((g) => (
                        <tr key={g.product_id}>
                          <td>{g.name}</td>
                          <td><code>{g.barcode}</code></td>
                          <td className="num">
                            <button
                              type="button"
                              className="btn-secondary btn-compact"
                              onClick={() => navigate(`/admin/labels?product=${g.product_id}&barcode=${g.barcode}`)}
                            >
                              {t('import.printLabels')}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            <div className="modal-buttons">
              <button type="button" className="btn-primary" onClick={onClose}>{t('common.close')}</button>
            </div>
          </div>
        ) : (
          <div className="modal-form">
            <p className="hint-text">
              {t('import.hint')}{' '}
              <button type="button" className="link-button" onClick={() => run(downloadImportTemplate)}>
                {t('import.downloadTemplate')}
              </button>
            </p>

            <label className="field-label">
              {t('import.file')}
              <input
                className="field-input"
                type="file"
                accept=".csv,.xlsx"
                disabled={busy}
                onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); }}
              />
            </label>

            <div className="form-row">
              <label className="field-label">
                {t('import.store')}
                <select
                  className="field-input"
                  value={options.store_id ?? ''}
                  disabled={busy}
                  onChange={(e) => changeOptions({ store_id: e.target.value ? Number(e.target.value) : null })}
                >
                  {stores.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <span className="hint-text">{t('import.storeHint')}</span>
              </label>
              <label className="field-label">
                {t('import.soldIn')}
                <select
                  className="field-input"
                  value={options.sold_in}
                  disabled={busy}
                  onChange={(e) => changeOptions({ sold_in: e.target.value as ImportOptions['sold_in'] })}
                >
                  <option value="all">{t('import.soldInAll')}</option>
                  <option value="store">{t('import.soldInStore')}</option>
                </select>
              </label>
            </div>
            <label className="field-label checkbox-label">
              <input
                type="checkbox"
                checked={options.generate_barcodes}
                disabled={busy}
                onChange={(e) => changeOptions({ generate_barcodes: e.target.checked })}
              />
              {t('import.generateBarcodes')}
            </label>

            {preview && (
              <>
                <div className="import-summary">
                  <span className="barcode-badge badge-inhouse">{t('import.creates', { count: preview.creates })}</span>
                  <span className="barcode-badge badge-manufacturer">{t('import.updates', { count: preview.updates })}</span>
                  <span className={`barcode-badge ${preview.errors ? 'badge-error' : 'badge-inhouse'}`}>
                    {t('import.errors', { count: preview.errors })}
                  </span>
                  <span className="hint-text">{t('import.total', { count: preview.total })}</span>
                </div>
                {preview.warnings.map((w) => <p key={w} className="hint-text">⚠ {w}</p>)}
                {preview.new_categories.length > 0 && (
                  <p className="hint-text">{t('import.willCreateCategories', { names: preview.new_categories.join(', ') })}</p>
                )}
                {preview.errors > 0 && <div className="page-error">{t('import.fixErrors')}</div>}

                <label className="field-label checkbox-label">
                  <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />
                  {t('import.onlyProblems')}
                </label>
                <div className="table-card import-table">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th className="num">{t('import.colRow')}</th>
                        <th>{t('import.colName')}</th>
                        <th>{t('import.colAction')}</th>
                        <th>{t('import.colNotes')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shownRows.length === 0 && (
                        <tr><td colSpan={4} className="empty-row">{t('import.noProblems')}</td></tr>
                      )}
                      {shownRows.map((r) => (
                        <tr key={r.row}>
                          <td className="num">{r.row}</td>
                          <td>{r.name}</td>
                          <td>
                            <span className={`barcode-badge ${r.action === 'error' ? 'badge-error' : r.action === 'update' ? 'badge-manufacturer' : 'badge-inhouse'}`}>
                              {t(`import.action.${r.action}`)}
                            </span>
                          </td>
                          <td>
                            {r.errors.map((m) => <div key={m} className="import-error">{m}</div>)}
                            {r.warnings.map((m) => <div key={m} className="import-warning">{m}</div>)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            <div className="modal-buttons">
              <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>{t('common.cancel')}</button>
              {preview && preview.errors === 0 ? (
                <button type="button" className="btn-primary" onClick={doImport} disabled={busy}>
                  {busy ? t('import.importing') : t('import.importBtn', { count: preview.creates + preview.updates })}
                </button>
              ) : (
                <button type="button" className="btn-primary" onClick={check} disabled={busy || !file}>
                  {busy ? t('import.checking') : preview ? t('import.checkAgain') : t('import.check')}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
