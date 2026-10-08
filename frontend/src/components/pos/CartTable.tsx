// Bill lines table.
import { useTranslation } from 'react-i18next';
import type { SaleItemOut } from '../../types/sale';
import { IconScan } from '../common/Icons';
import { CartRow } from './CartRow';

interface Props {
  items: SaleItemOut[];
  disabled: boolean;
  onQtyChange: (itemId: number, qty: number) => void;
  onRemove: (itemId: number) => void;
  onManualDiscount: (item: SaleItemOut) => void;
}

export function CartTable({ items, disabled, onQtyChange, onRemove, onManualDiscount }: Props) {
  const { t } = useTranslation();
  return (
    <table className="data-table cart-table">
      <thead>
        <tr>
          <th style={{ width: '40px' }}>#</th>
          <th>{t('pos.colItem')}</th>
          <th className="num" style={{ width: '100px' }}>{t('pos.colPrice')}</th>
          <th className="num" style={{ width: '130px' }}>{t('pos.colQty')}</th>
          <th className="num" style={{ width: '110px' }}>{t('pos.colTotal')}</th>
          <th style={{ width: '84px' }} />
        </tr>
      </thead>
      <tbody>
        {items.length === 0 && (
          <tr>
            <td colSpan={6} className="empty-row cart-empty-state">
              <div className="empty-cart-icon">
                <IconScan size={42} />
              </div>
              <div className="empty-cart-title">{t('pos.emptyTitle')}</div>
              <p className="empty-cart-hint">{t('pos.emptyHint')}</p>
            </td>
          </tr>
        )}
        {items.map((item, i) => (
          <CartRow
            key={item.id}
            item={item}
            index={i}
            disabled={disabled}
            onQtyChange={onQtyChange}
            onRemove={onRemove}
            onManualDiscount={onManualDiscount}
          />
        ))}
      </tbody>
    </table>
  );
}

