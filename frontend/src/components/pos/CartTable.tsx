// Bill lines table.
import type { SaleItemOut } from '../../types/sale';
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
          <th>#</th>
          <th>Item</th>
          <th className="num">Price</th>
          <th className="num">Qty</th>
          <th className="num">Amount</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {items.length === 0 && (
          <tr>
            <td colSpan={6} className="empty-row">Scan an item to start the bill.</td>
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
