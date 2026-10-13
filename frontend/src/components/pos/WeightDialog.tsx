// Weight for a loose item picked by name (no scale sticker, or a torn one): "1.250" kg or "750 g".
import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import type { ProductOut } from '../../types/product';
import { formatRupees } from '../../utils/money';
import { IconX } from '../common/Icons';

/** "1.25" / "1.25 kg" -> 1.25; "750 g" / "750gm" -> 0.75. null = not a weight. */
export function parseWeight(text: string): number | null {
  const m = /^(\d+(?:\.\d+)?|\.\d+)\s*(kg|kgs|g|gm|gms|gram|grams)?$/.exec(text.trim().toLowerCase());
  if (!m) return null;
  const value = Number(m[1]);
  const kg = m[2] && m[2] !== 'kg' && m[2] !== 'kgs' ? value / 1000 : value;
  const rounded = Math.round(kg * 1000) / 1000;
  return rounded >= 0.001 && rounded <= 9999 ? rounded : null;
}

interface Props {
  product: ProductOut;
  busy: boolean;
  onConfirm: (kg: number) => void;
  onClose: () => void;
}

export function WeightDialog({ product, busy, onConfirm, onClose }: Props) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  useKeyboardShortcuts({ Escape: onClose });

  const kg = parseWeight(text);
  const unit = product.uom || 'kg';
  const rate = Number(product.store_price ?? product.price);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (kg !== null) onConfirm(kg);
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="modal-subtitle">{t('weight.subtitle')}</span>
            <h3 className="modal-title">{product.name}</h3>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose}>
            <IconX size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-form">
          <label className="field-label">
            <span>{t('weight.label', { unit })}</span>
            <input
              className="field-input pay-amount"
              inputMode="decimal"
              autoComplete="off"
              value={text}
              placeholder="1.250"
              onChange={(e) => setText(e.target.value)}
              autoFocus
            />
            <span className="hint-text">{t('weight.hint')}</span>
          </label>

          <p className="hint-text">
            {kg !== null
              ? t('weight.preview', { rate: formatRupees(rate), unit, kg: kg.toFixed(3), amount: formatRupees(rate * kg) })
              : text.trim() ? t('weight.invalid') : t('weight.rate', { rate: formatRupees(rate), unit })}
          </p>

          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onClose}>
              {t('common.cancel')}
            </button>
            <button type="submit" className="btn-primary" disabled={busy || kg === null}>
              {t('weight.add')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
