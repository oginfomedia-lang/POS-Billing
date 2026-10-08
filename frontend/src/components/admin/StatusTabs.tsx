// Active / Inactive switch for lists whose items can be deactivated, so deactivated
// products, users, stores, counters and offers live in their own view.
import { useTranslation } from 'react-i18next';

export type StatusView = 'active' | 'inactive';

interface Props {
  value: StatusView;
  onChange: (view: StatusView) => void;
  /** Optional counts shown as small pills (only when the whole list is loaded). */
  counts?: Record<StatusView, number>;
  /** Defaults to "Deactivated" in the current language. */
  inactiveLabel?: string;
}

export function StatusTabs({ value, onChange, counts, inactiveLabel }: Props) {
  const { t } = useTranslation();
  return (
    <div className="tab-bar" role="tablist">
      {(['active', 'inactive'] as StatusView[]).map((view) => (
        <button
          key={view}
          type="button"
          role="tab"
          aria-selected={value === view}
          className={`tab${value === view ? ' active' : ''}`}
          onClick={() => onChange(view)}
        >
          {view === 'active' ? t('common.active') : inactiveLabel ?? t('common.deactivated')}
          {counts && <span className="tab-count">{counts[view]}</span>}
        </button>
      ))}
    </div>
  );
}
