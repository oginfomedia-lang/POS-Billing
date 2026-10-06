// F-key shortcuts for the POS screen.
import { useEffect, useRef } from 'react';

/** keys are KeyboardEvent.key values, e.g. { F12: pay, Escape: voidBill }. */
export function useKeyboardShortcuts(handlers: Record<string, () => void>, enabled = true): void {
  // Keep the latest handlers without re-binding the listener on every render.
  const ref = useRef(handlers);
  ref.current = handlers;

  useEffect(() => {
    if (!enabled) return;
    function onKeyDown(e: KeyboardEvent) {
      const handler = ref.current[e.key];
      if (!handler) return;
      e.preventDefault();
      handler();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [enabled]);
}
