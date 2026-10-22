// POS landing: checks for an active shift, then redirects to billing or shift-open.
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { hasOfflineSupport } from '../../offline/sync';
import { getHealth } from '../../services/api/healthApi';
import { useAuthStore } from '../../store/authStore';
import { useOfflineStore } from '../../store/offlineStore';
import { useShiftStore } from '../../store/shiftStore';

export function PosPage() {
  const { t } = useTranslation();
  const { loadActive } = useShiftStore();
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    loadActive().then(() => {
      if (!cancelled) {
        const shift = useShiftStore.getState().shift;
        // Server unreachable but this cashier has a shift open on this PC: bill offline.
        const last = useOfflineStore.getState().lastShift;
        if (!shift && hasOfflineSupport() && last && last.user_id === useAuthStore.getState().user?.id) {
          getHealth()
            .then(() => !cancelled && navigate('/pos/shift/open', { replace: true }))
            .catch(() => !cancelled && navigate('/pos/offline', { replace: true }));
          return;
        }
        navigate(shift ? '/pos/billing' : '/pos/shift/open', { replace: true });
      }
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="admin-page">
      <p className="loading-text">{t('common.loading')}</p>
    </div>
  );
}
