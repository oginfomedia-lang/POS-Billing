// "All stores" / single-store picker used by the dashboard and reports.
import { useEffect, useState } from 'react';
import { listStores } from '../../services/api/storeApi';
import type { StoreOut } from '../../types/api';

interface Props {
  value: number | null;
  onChange: (storeId: number | null) => void;
}

export function StoreFilter({ value, onChange }: Props) {
  const [stores, setStores] = useState<StoreOut[]>([]);

  useEffect(() => {
    listStores().then(setStores).catch(() => setStores([]));
  }, []);

  // One store: nothing to choose.
  if (stores.length <= 1) return null;

  return (
    <select
      className="field-input filter-input"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">All stores</option>
      {stores.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
    </select>
  );
}
