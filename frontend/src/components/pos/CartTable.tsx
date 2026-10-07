// Bill lines table.
import type { SaleItemOut } from '../../types/sale';
import { IconScan } from '../common/Icons';
import { CartRow } from './CartRow';

interface Props {
  items: SaleItemOut[];
  disabled: boolean;
  onQtyChange: (itemId: number, qty: number) => void;
  onRemove: (itemId: number) => void;
}

export function CartTable({ items, disabled, onQtyChange, onRemove }: Props) {
  return (
    <table className="data-table cart-table">
      <thead>
        <tr>
          <th style={{ width: '40px' }}>#</th>
          <th>Item Details</th>
          <th className="num" style={{ width: '100px' }}>Price</th>
          <th className="num" style={{ width: '130px' }}>Quantity</th>
          <th className="num" style={{ width: '110px' }}>Total</th>
          <th style={{ width: '50px' }} />
        </tr>
      </thead>
      <tbody>
        {items.length === 0 && (
          <tr>
            <td colSpan={6} className="empty-row cart-empty-state">
              <div className="empty-cart-icon">
                <IconScan size={42} />
              </div>
              <div className="empty-cart-title">Cart is empty</div>
              <p className="empty-cart-hint">Scan product barcode or enter item code to start billing</p>
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
          />
        ))}
      </tbody>
    </table>
  );
}

