// One bill line (name, qty, price, total).
import { useEffect, useState } from 'react';
import type { SaleItemOut } from '../../types/sale';
import { formatRupees } from '../../utils/money';

interface Props {
  item: SaleItemOut;
  index: number;
  disabled: boolean;
  onQtyChange: (itemId: number, qty: number) => void;
  onRemove: (itemId: number) => void;
}

export function CartRow({ item, index, disabled, onQtyChange, onRemove }: Props) {
  const [qty, setQty] = useState(String(item.qty));

  // Re-sync when the server changes the qty (e.g. the same product is scanned again).
  useEffect(() => setQty(String(item.qty)), [item.qty]);

  function commit() {
    const n = Number(qty);
    if (!Number.isInteger(n) || n < 1 || n > 9999) {
      setQty(String(item.qty));
      return;
    }
    if (n !== item.qty) onQtyChange(item.id, n);
  }

  return (
    <tr>
      <td>{index + 1}</td>
      <td>{item.product_name}</td>
      <td className="num">{formatRupees(item.unit_price)}</td>
      <td className="num">
        <input
          className="qty-input"
          type="number"
          min={1}
          max={9999}
          value={qty}
          disabled={disabled}
          onChange={(e) => setQty(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
        />
      </td>
      <td className="num">{formatRupees(item.line_total)}</td>
      <td>
        <button className="btn-sm" disabled={disabled} onClick={() => onRemove(item.id)} title="Remove line">
          ✕
        </button>
      </td>
    </tr>
  );
}
