// Branch switcher in the admin sidebar. Head office picks any branch (or all of them);
// a branch manager just sees their own branch's name.
import { useTranslation } from 'react-i18next';
import { useCanSwitchStore, useStoreContext, useStoreDisplayName, useStores } from '../../store/storeContext';
import { IconStore } from '../common/Icons';

export function StoreSwitcher() {
  const { t } = useTranslation();
  const stores = useStores().filter((s) => s.is_active);
  const selectedId = useStoreContext((s) => s.selectedId);
  const select = useStoreContext((s) => s.select);
  const canSwitch = useCanSwitchStore();
  const name = useStoreDisplayName();

  return (
    <div className="store-switcher">
      <span className="store-switcher-label">
        <IconStore size={13} /> {t('stores.switcherLabel')}
      </span>
      {canSwitch && stores.length > 1 ? (
        <select
          className="store-switcher-select"
          value={selectedId ?? ''}
          onChange={(e) => select(e.target.value ? Number(e.target.value) : null)}
          aria-label={t('stores.switcherLabel')}
        >
          <option value="">{t('stores.allBranches')}</option>
          {stores.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      ) : (
        <div className="store-switcher-fixed" title={canSwitch ? undefined : t('stores.lockedHint')}>
          {name}
        </div>
      )}
    </div>
  );
}
