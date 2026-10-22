// A text box with phonetic Marathi typing, used in place of <input> / <textarea> for names and other text
// that may be written in Marathi. The EN | म switch (or Ctrl+M / Cmd+M while typing) changes the mode:
//   EN: an ordinary text box.
//   म:  type Roman letters ("sakhar"); suggestions appear; Space (or Enter / a click on a suggestion) puts in
//       the Devanagari word (साखर). Backspace straight afterwards brings "sakhar" back. ↑ ↓ pick another
//       suggestion; Esc keeps the letters as typed. Leaving the box converts the last word too.
// Conversion is local (no network). The value given to onChange is exactly what is shown, so forms save
// Devanagari as typed.
import {
  type ChangeEvent,
  type FocusEvent,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type SyntheticEvent,
  type TextareaHTMLAttributes,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { getTypingMode, learnedChoices, rememberChoice, setTypingMode, type TypingMode } from '../../utils/marathi/prefs';
import { suggest } from '../../utils/marathi/transliterate';
import { type Commit, type CaretWord, commitWord, undoCommit, wordBeforeCaret } from '../../utils/marathi/typing';

type Field = HTMLInputElement | HTMLTextAreaElement;

export interface MarathiInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type'> {
  value: string;
  /** The new text (not the event): conversions change the text without a native input event. */
  onChange: (value: string) => void;
  /** false = a plain text box with no EN | म switch. */
  transliterationEnabled?: boolean;
  /** A <textarea> instead of an <input>. */
  multiline?: boolean;
  rows?: number;
}

interface Popup {
  start: number;
  word: string;
  items: string[];
  active: number;
}

export function MarathiInput({
  value,
  onChange,
  transliterationEnabled = true,
  multiline = false,
  rows,
  className,
  onKeyDown,
  onBlur,
  ...rest
}: MarathiInputProps) {
  const { t } = useTranslation();
  const enabled = transliterationEnabled && !rest.disabled && !rest.readOnly;
  const [mode, setMode] = useState<TypingMode>(() => (transliterationEnabled ? getTypingMode() : 'en'));
  const marathi = enabled && mode === 'mr';
  const [popup, setPopup] = useState<Popup | null>(null);

  const field = useRef<Field | null>(null);
  const lastCommit = useRef<Commit | null>(null); // for Backspace / Ctrl+Z straight after a conversion
  const dismissed = useRef<CaretWord | null>(null); // Esc: leave this word as typed
  const pendingCaret = useRef<number | null>(null);
  const listId = useId();

  // After a conversion the text changes from here, so put the caret where it belongs.
  useLayoutEffect(() => {
    const node = field.current;
    if (node && pendingCaret.current !== null) {
      node.setSelectionRange(pendingCaret.current, pendingCaret.current);
      pendingCaret.current = null;
    }
  }, [value]);

  function isDismissed(w: CaretWord): boolean {
    const d = dismissed.current;
    return d !== null && d.start === w.start && d.word === w.word;
  }

  function refresh(text: string, caret: number, on: boolean = marathi) {
    const w = on ? wordBeforeCaret(text, caret) : null;
    if (!w || isDismissed(w)) {
      setPopup(null);
      return;
    }
    const items = suggest(w.word, learnedChoices());
    setPopup(items.length > 0 ? { start: w.start, word: w.word, items, active: 0 } : null);
  }

  function apply(text: string, caret: number) {
    pendingCaret.current = caret;
    onChange(text);
  }

  /** Puts `choice` in place of the word before the caret. false if there's nothing to convert. */
  function convert(choice: string | undefined, addSpace: boolean): boolean {
    const node = field.current;
    if (!node || node.selectionStart !== node.selectionEnd) return false;
    const w = wordBeforeCaret(value, node.selectionStart ?? value.length);
    if (!w || isDismissed(w)) return false;
    const pick = choice ?? suggest(w.word, learnedChoices())[0];
    if (!pick) return false;
    const res = commitWord(value, w, pick, addSpace);
    if (rest.maxLength !== undefined && rest.maxLength >= 0 && res.value.length > rest.maxLength) return false;
    lastCommit.current = res.commit;
    dismissed.current = null;
    setPopup(null);
    apply(res.value, res.caret);
    return true;
  }

  function choose(index: number, addSpace: boolean) {
    if (!popup) return;
    const pick = popup.items[index];
    if (index > 0) rememberChoice(popup.word, pick); // offered first next time
    convert(pick, addSpace);
  }

  function toggle() {
    const next: TypingMode = mode === 'en' ? 'mr' : 'en';
    setMode(next);
    setTypingMode(next); // the next box opened starts in this mode
    dismissed.current = null;
    const node = field.current;
    if (node) refresh(node.value, node.selectionStart ?? node.value.length, enabled && next === 'mr');
  }

  function handleChange(e: ChangeEvent<Field>) {
    lastCommit.current = null; // the user edited: Backspace works normally again
    onChange(e.target.value);
    refresh(e.target.value, e.target.selectionStart ?? e.target.value.length);
  }

  function handleSelect(e: SyntheticEvent<Field>) {
    // Caret moved (click, arrow keys): suggestions follow the word at the caret, if any.
    const node = e.currentTarget;
    if (marathi) refresh(node.value, node.selectionStart ?? node.value.length);
  }

  function handleKeyDown(e: KeyboardEvent<Field>) {
    (onKeyDown as ((ev: KeyboardEvent<Field>) => void) | undefined)?.(e);
    if (e.defaultPrevented || e.nativeEvent.isComposing) return;
    const ctrl = e.ctrlKey || e.metaKey;
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;

    // Ctrl+M / Cmd+M: switch EN | म (also stops the window's own Ctrl+M "minimise").
    if (enabled && ctrl && !e.altKey && !e.shiftKey && key === 'm') {
      e.preventDefault();
      toggle();
      return;
    }
    if (!marathi) return;

    if (popup) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        e.stopPropagation(); // the suggestion list handles it, not page-wide shortcuts
        const step = e.key === 'ArrowDown' ? 1 : -1;
        setPopup({ ...popup, active: (popup.active + step + popup.items.length) % popup.items.length });
        return;
      }
      if (e.key === 'Enter' && !ctrl && !e.altKey && !e.shiftKey) {
        e.preventDefault(); // pick the suggestion; the form isn't submitted
        e.stopPropagation();
        choose(popup.active, false);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation(); // don't close the dialog / leave the page as well
        dismissed.current = { start: popup.start, end: popup.start + popup.word.length, word: popup.word };
        setPopup(null);
        return;
      }
    }

    if (e.key === ' ' && !ctrl && !e.altKey) {
      if (popup) {
        if (convert(popup.items[popup.active], true)) {
          e.preventDefault();
          if (popup.active > 0) rememberChoice(popup.word, popup.items[popup.active]);
        }
      } else if (convert(undefined, true)) {
        e.preventDefault();
      }
      return;
    }

    // Backspace (or Ctrl+Z) straight after a conversion: the typed letters come back.
    if ((e.key === 'Backspace' && !ctrl && !e.altKey) || (ctrl && !e.altKey && !e.shiftKey && key === 'z')) {
      const node = field.current;
      const c = lastCommit.current;
      if (!node || !c || node.selectionStart !== node.selectionEnd) return;
      const res = undoCommit(value, node.selectionStart ?? 0, c);
      if (!res) return;
      e.preventDefault();
      lastCommit.current = null;
      dismissed.current = null;
      apply(res.value, res.caret);
      refresh(res.value, res.caret);
    }
  }

  function handleBlur(e: FocusEvent<Field>) {
    // Leaving the box (e.g. clicking Save) converts the word still being typed.
    if (marathi) convert(popup ? popup.items[popup.active] : undefined, false);
    setPopup(null);
    lastCommit.current = null;
    (onBlur as ((ev: FocusEvent<Field>) => void) | undefined)?.(e);
  }

  const fieldProps = {
    ...rest,
    className: `${className ?? 'field-input'}${transliterationEnabled ? ' mr-field' : ''}`,
    value,
    onChange: handleChange,
    onKeyDown: handleKeyDown,
    onBlur: handleBlur,
    onSelect: handleSelect,
    lang: marathi ? 'mr' : rest.lang,
    autoComplete: rest.autoComplete ?? 'off',
    'aria-autocomplete': transliterationEnabled ? ('list' as const) : undefined,
    'aria-expanded': transliterationEnabled ? popup !== null : undefined,
    'aria-controls': popup ? listId : undefined,
    'aria-activedescendant': popup ? `${listId}-${popup.active}` : undefined,
  };

  return (
    <div className={`mr-input${multiline ? ' mr-input-multi' : ''}`}>
      {multiline ? (
        <textarea
          {...(fieldProps as unknown as TextareaHTMLAttributes<HTMLTextAreaElement>)}
          rows={rows}
          ref={(node) => { field.current = node; }}
        />
      ) : (
        <input {...fieldProps} type="text" ref={(node) => { field.current = node; }} />
      )}

      {transliterationEnabled && (
        <button
          type="button"
          className={`mr-toggle mr-toggle-${mode}`}
          aria-pressed={mode === 'mr'}
          aria-label={t('marathi.toggleLabel')}
          title={t('marathi.toggleTitle')}
          disabled={!enabled}
          onMouseDown={(e) => e.preventDefault()} // keep the caret in the text box
          onClick={() => { toggle(); field.current?.focus(); }}
        >
          <span className="mr-toggle-en">EN</span>
          <span className="mr-toggle-mr">म</span>
        </button>
      )}

      {popup && (
        <ul className="mr-suggest" role="listbox" id={listId} aria-label={t('marathi.suggestions')}>
          {popup.items.map((s, i) => (
            <li
              key={s}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === popup.active}
              className={i === popup.active ? 'active' : undefined}
              onMouseDown={(e) => { e.preventDefault(); choose(i, true); }}
            >
              {s}
            </li>
          ))}
          <li className="mr-suggest-hint" aria-hidden="true">{t('marathi.hint', { word: popup.word })}</li>
        </ul>
      )}
    </div>
  );
}
