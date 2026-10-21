// Text editing for Marathi typing mode, kept apart from the UI so it can be unit-tested:
// which Roman word the cursor is at the end of, replacing it with its Devanagari spelling, and undoing
// that replacement with Backspace straight afterwards (like a phone keyboard).
// Self-contained (no imports) so the unit tests can run it directly with Node.

export interface CaretWord {
  start: number; // index of the word's first letter
  end: number; // index just after its last letter (= the caret)
  word: string;
}

/** The last conversion, so Backspace right after it can bring the typed letters back. */
export interface Commit {
  start: number;
  roman: string;
  converted: string;
  valueAfter: string;
  caretAfter: number;
  addedSpace: boolean; // the conversion put in the space after the word (Undo removes only that one)
}

const WORD_CHAR = /[A-Za-z.]/;
// A letter run touching one of these is part of a code, number, email or URL: "A12", "x@y.in", "a/b".
const CODE_CHAR = /[0-9@_/\\:-]/;

/**
 * The Roman word that ends exactly at the caret, or null: caret in the middle of a word, no letters before
 * it, or the letters belong to a code / email / URL.
 */
export function wordBeforeCaret(value: string, caret: number): CaretWord | null {
  if (caret <= 0 || caret > value.length) return null;
  if (/[A-Za-z]/.test(value[caret] ?? '')) return null; // caret in the middle of a word
  let start = caret;
  while (start > 0 && WORD_CHAR.test(value[start - 1])) start--;
  // Dots belong to a word only as ".n" / ".N" inside it ("sa.nt"); a leading or final dot is punctuation.
  while (start < caret && value[start] === '.') start++;
  const word = value.slice(start, caret);
  if (!/^[A-Za-z](?:[A-Za-z]|\.[nN])*$/.test(word)) return null; // e.g. caret just after a full stop
  if (CODE_CHAR.test(value[start - 1] ?? '') || CODE_CHAR.test(value[caret] ?? '')) return null;
  return { start, end: caret, word };
}

/**
 * Replaces the word with its Devanagari spelling. With `addSpace`, a space follows it (the Space key that
 * triggered it) unless one is already there, in which case the caret just moves past it.
 */
export function commitWord(
  value: string,
  w: CaretWord,
  converted: string,
  addSpace: boolean,
): { value: string; caret: number; commit: Commit } {
  const before = value.slice(0, w.start);
  let after = value.slice(w.end);
  let caret = w.start + converted.length;
  let addedSpace = false;
  if (addSpace) {
    if (!after.startsWith(' ')) {
      after = ' ' + after;
      addedSpace = true;
    }
    caret += 1;
  }
  const next = before + converted + after;
  return {
    value: next,
    caret,
    commit: { start: w.start, roman: w.word, converted, valueAfter: next, caretAfter: caret, addedSpace },
  };
}

/**
 * Backspace (or Ctrl+Z) straight after a conversion: the typed Roman word comes back, without the space the
 * conversion added. Null when anything has changed since (other typing, caret moved), so the key works as usual.
 */
export function undoCommit(value: string, caret: number, c: Commit): { value: string; caret: number } | null {
  if (value !== c.valueAfter || caret !== c.caretAfter) return null;
  const head = value.slice(0, c.start);
  let tail = value.slice(c.start + c.converted.length);
  if (c.addedSpace) tail = tail.slice(1);
  return { value: head + c.roman + tail, caret: c.start + c.roman.length };
}
