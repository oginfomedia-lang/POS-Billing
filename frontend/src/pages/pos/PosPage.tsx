// POS landing: checks for an active shift, then redirects to billing or shift-open.
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useShiftStore } from '../../store/shiftStore';

export function PosPage() {
  const { loadActive } = useShiftStore();
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    loadActive().then(() => {
      if (!cancelled) {
        const shift = useShiftStore.getState().shift;
        navigate(shift ? '/pos/billing' : '/pos/shift/open', { replace: true });
      }
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="admin-page">
      <p className="loading-text">Loading…</p>
    </div>
  );
}
