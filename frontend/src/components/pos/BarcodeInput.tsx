// Always-focused input that receives scanner keystrokes.
// USB scanners type the code and press Enter, so a plain input handles both scanning and typing.
import { type KeyboardEvent, useEffect, useRef, useState } from 'react';
import { IconScan, IconX } from '../common/Icons';

interface Props {
  onScan: (code: string) => void;
  /** Refocuses the input whenever it becomes true (e.g. after a dialog closes). */
  active: boolean;
}

export function BarcodeInput({ onScan, active }: Props) {
  const [value, setValue] = useState('');
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (active) ref.current?.focus();
  }, [active]);

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const code = value.trim();
    setValue('');
    if (code) onScan(code);
  }

  return (
    <div className="barcode-input-wrapper">
      <div className="barcode-scanner-icon" title="Barcode scanner active">
        <IconScan size={22} />
      </div>
      <input
        ref={ref}
        className="field-input barcode-input"
        placeholder="Scan barcode or search product SKU/Name (Enter to add)..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        autoFocus
      />
      {value ? (
        <button
          type="button"
          className="barcode-clear-btn"
          onClick={() => {
            setValue('');
            ref.current?.focus();
          }}
          title="Clear"
        >
          <IconX size={16} />
        </button>
      ) : (
        <span className="scanner-badge">
          <span className="scanner-dot" />
          Ready
        </span>
      )}
    </div>
  );
}

