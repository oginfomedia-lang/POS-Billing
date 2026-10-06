// Shows keyboard shortcut hints (F2 Hold, F3 Held Bills, F12 Pay, Esc Void). Each hint is also clickable.

export interface Shortcut {
  key: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

export function ShortcutBar({ shortcuts }: { shortcuts: Shortcut[] }) {
  return (
    <div className="shortcut-bar">
      {shortcuts.map((s) => (
        <button key={s.key} className="shortcut" disabled={s.disabled} onClick={s.onClick}>
          <kbd>{s.key}</kbd> {s.label}
        </button>
      ))}
    </div>
  );
}
