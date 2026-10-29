// App-wide rules for <input type="number">, so a number changes only when it is typed:
//   - the mouse wheel over a focused box doesn't change it (the box lets go of focus and the page scrolls);
//   - ↑ / ↓ don't step it (the up/down arrows are hidden in global.css);
//   - a box showing 0 has the 0 selected when entered, so typing "220" gives 220, not 0220.

function numberInput(target: EventTarget | null): HTMLInputElement | null {
  return target instanceof HTMLInputElement && target.type === 'number' ? target : null;
}

export function installNumberInputGuards(): void {
  document.addEventListener(
    'wheel',
    (e) => {
      const input = numberInput(e.target);
      if (input && input === document.activeElement) input.blur();
    },
    { capture: true, passive: true },
  );

  document.addEventListener(
    'keydown',
    (e) => {
      if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') && numberInput(e.target)) e.preventDefault();
    },
    true,
  );

  // Entered with a click: the mouse button going up would put the caret back in place of the selection.
  let byMouse = false;
  document.addEventListener('mousedown', () => { byMouse = true; }, true);
  document.addEventListener('mouseup', () => { byMouse = false; }, true);
  document.addEventListener(
    'focusin',
    (e) => {
      const input = numberInput(e.target);
      if (!input || input.value === '' || Number(input.value) !== 0) return;
      input.select();
      if (byMouse) input.addEventListener('mouseup', (ev) => ev.preventDefault(), { once: true });
    },
    true,
  );
}
