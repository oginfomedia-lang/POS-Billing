// Shows keyboard shortcut hints (F2 Hold, F3 Held Bills, F12 Pay, Esc Void). Each hint is also clickable.
import React from 'react';

export interface Shortcut {
  key: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  icon?: React.FC<{ size?: number }>;
  variant?: 'primary' | 'warning' | 'danger' | 'default';
}

export function ShortcutBar({ shortcuts }: { shortcuts: Shortcut[] }) {
  return (
    <div className="shortcut-bar">
      {shortcuts.map((s) => {
        const Icon = s.icon;
        return (
          <button
            key={s.key}
            className={`shortcut shortcut-${s.variant || 'default'}`}
            disabled={s.disabled}
            onClick={s.onClick}
          >
            <kbd>{s.key}</kbd>
            {Icon && <Icon size={15} />}
            <span>{s.label}</span>
          </button>
        );
      })}
    </div>
  );
}

