// Settings → Weighing scale: scan a sticker printed by the scale and see what the system reads from it.
// The way to find the right format when nobody knows how the scale is set up.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getProductByBarcode } from '../../services/api/productApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { ProductBarcodeOut } from '../../types/product';
import { formatRupees } from '../../utils/money';

export function ScaleTestBox({ unsaved }: { unsaved: boolean }) {
  const { t } = useTranslation();
  const [code, setCode] = useState('');
  const [result, setResult] = useState<ProductBarcodeOut | null>(null);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);

  async function test() {
    if (!code.trim()) return;
    setChecking(true);
    setError('');
    setResult(null);
    try {
      setResult(await getProductByBarcode(code.trim()));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="field-label">
      <span>{t('settings.scale.testTitle')}</span>
      {/* A div, not a form: this sits inside the settings form. */}
      <div className="barcode-scanner-box">
        <input
          className="field-input"
          style={{ flex: 1 }}
          inputMode="numeric"
          value={code}
          placeholder="2000123012505"
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); test(); } }}
        />
        <button type="button" className="btn-secondary" disabled={checking || !code} onClick={() => test()}>
          {checking ? t('settings.scale.testing') : t('settings.scale.test')}
        </button>
      </div>
      {unsaved && <span className="hint-text">{t('settings.scale.saveFirst')}</span>}
      {result && (
        <div className="notice-bar">
          {result.weight_kg != null
            ? t('settings.scale.testOk', {
                name: result.product.name,
                kg: result.weight_kg.toFixed(3),
                amount: formatRupees(result.calculated_price ?? 0),
              })
            : t('settings.scale.testNotScale', { name: result.product.name })}
        </div>
      )}
      {error && <div className="page-error">{error}</div>}
    </div>
  );
}
