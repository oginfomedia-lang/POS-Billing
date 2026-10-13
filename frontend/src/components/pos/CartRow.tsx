// One bill line (name, qty, price, total). Loose items (sugar, dal…) take a weight in kg with decimals.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { SaleItemOut } from '../../types/sale';
import { formatRupees } from '../../utils/money';
import { IconMinus, IconPercent, IconPlus, IconTrash } from '../common/Icons';

/** +/− on a loose item changes the weight by this much (kg). */
const WEIGHT_STEP = 0.5;

/** 1.25 -> "1.25", 2 -> "2"; never more than 3 decimals (grams). */
function weightText(kg: number): string {
  return String(Math.round(kg * 1000) / 1000);
}

interface Props {
  item: SaleItemOut;
  index: number;
  disabled: boolean;
  onQtyChange: (itemId: number, qty: number) => void;
  onRemove: (itemId: number) => void;
  onManualDiscount: (item: SaleItemOut) => void;
}

export function CartRow({ item, index, disabled, onQtyChange, onRemove, onManualDiscount }: Props) {
  const { t } = useTranslation();
  const loose = item.is_variable_weight;
  const [qty, setQty] = useState(String(item.qty));
  // Show the MRP only when it is above our price incl. GST (i.e. the customer actually saves).
  const priceWithGst = Number(item.unit_price) * (1 + Number(item.tax_rate) / 100);
  const showMrp = item.mrp !== null && Number(item.mrp) > priceWithGst + 0.005;

  // Re-sync when the server changes the qty (e.g. the same product is scanned again).
  useEffect(() => setQty(String(item.qty)), [item.qty]);

  function commit(newQty?: number) {
    let target = newQty ?? Number(qty);
    if (loose) target = Math.round(target * 1000) / 1000;
    const valid = loose
      ? Number.isFinite(target) && target >= 0.001 && target <= 9999
      : Number.isInteger(target) && target >= 1 && target <= 9999;
    if (!valid) {
      setQty(String(item.qty));
      return;
    }
    if (target !== item.qty) {
      setQty(String(target));
      onQtyChange(item.id, target);
    }
  }

  function handleDecrement() {
    const step = loose ? WEIGHT_STEP : 1;
    if (item.qty > step) {
      commit(item.qty - step);
    } else {
      onRemove(item.id);
    }
  }

  function handleIncrement() {
    commit(item.qty + (loose ? WEIGHT_STEP : 1));
  }

  return (
    <tr className="cart-item-row">
      <td className="row-index">{index + 1}</td>
      <td className="item-name-cell">
        <span className="product-title">{item.product_name}</span>
        {showMrp && <span className="mrp-tag">{t('pos.mrp', { mrp: formatRupees(item.mrp!) })}</span>}
      </td>
      <td className="num unit-price-cell">
        {formatRupees(item.unit_price)}
        {loose && <span className="qty-unit">/{item.uom}</span>}
      </td>
      <td className="num qty-cell">
        <div className="qty-stepper">
          <button
            type="button"
            className="stepper-btn stepper-btn-minus"
            disabled={disabled}
            onClick={handleDecrement}
            title={t('pos.decreaseQty')}
          >
            <IconMinus size={14} />
          </button>
          <input
            className={loose ? 'qty-input qty-input-weight' : 'qty-input'}
            type="number"
            min={loose ? 0.001 : 1}
            max={9999}
            step={loose ? 0.001 : 1}
            inputMode={loose ? 'decimal' : 'numeric'}
            title={loose ? t('pos.weightTitle') : undefined}
            value={loose && qty === String(item.qty) ? weightText(item.qty) : qty}
            disabled={disabled}
            onChange={(e) => setQty(e.target.value)}
            onBlur={() => commit()}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
          />
          <button
            type="button"
            className="stepper-btn stepper-btn-plus"
            disabled={disabled}
            onClick={handleIncrement}
            title={t('pos.increaseQty')}
          >
            <IconPlus size={14} />
          </button>
        </div>
        {loose && <span className="qty-unit">{item.uom}</span>}
      </td>
      <td className="num line-total-cell">
        <div className="line-total-val">{formatRupees(item.line_total)}</div>
        {Number(item.offer_discount) > 0 && (
          <div className="line-discount-badge" title={item.offer_name ?? undefined}>
            {item.offer_name} − {formatRupees(item.offer_discount)}
          </div>
        )}
        {Number(item.manual_discount) > 0 && (
          <div className="line-discount-badge line-discount-manual" title={item.manual_discount_reason ?? undefined}>
            {t('pos.manual')} − {formatRupees(item.manual_discount)}
          </div>
        )}
      </td>
      <td className="actions-cell">
        <button
          className="btn-line-discount"
          disabled={disabled}
          onClick={() => onManualDiscount(item)}
          title={t('pos.manualDiscountTitle')}
        >
          <IconPercent size={16} />
        </button>
        <button
          className="btn-remove-line"
          disabled={disabled}
          onClick={() => onRemove(item.id)}
          title={t('pos.removeLine')}
        >
          <IconTrash size={16} />
        </button>
      </td>
    </tr>
  );
}

