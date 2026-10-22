// Marathi typing settings kept on this PC (browser storage; the app works the same if it's unavailable):
// the typing mode new fields start in, and the spellings users picked from the suggestions, which are then
// offered first for the same Roman word.

export type TypingMode = 'en' | 'mr';

const MODE_KEY = 'pos-typing-mode';
const CHOICES_KEY = 'pos-marathi-choices';
const MAX_CHOICES = 300;

let choices: Record<string, string> | null = null;

/** The mode new text fields start in: the one last chosen with the EN | म switch. English by default. */
export function getTypingMode(): TypingMode {
  try {
    return localStorage.getItem(MODE_KEY) === 'mr' ? 'mr' : 'en';
  } catch {
    return 'en';
  }
}

export function setTypingMode(mode: TypingMode): void {
  try {
    localStorage.setItem(MODE_KEY, mode);
  } catch { /* storage unavailable: the switch still works for this field */ }
}

/** { romanWordLowercase: Devanagari } picked by users on this PC. */
export function learnedChoices(): Record<string, string> {
  if (choices === null) {
    try {
      const raw = JSON.parse(localStorage.getItem(CHOICES_KEY) ?? '{}');
      choices = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
    } catch {
      choices = {};
    }
  }
  return choices as Record<string, string>;
}

/** Remember a spelling picked from the suggestions (newest kept; the oldest dropped past MAX_CHOICES). */
export function rememberChoice(roman: string, word: string): void {
  const all = { ...learnedChoices() };
  const key = roman.toLowerCase();
  delete all[key];
  all[key] = word;
  const keys = Object.keys(all);
  for (const old of keys.slice(0, Math.max(0, keys.length - MAX_CHOICES))) delete all[old];
  choices = all;
  try {
    localStorage.setItem(CHOICES_KEY, JSON.stringify(all));
  } catch { /* kept for this session only */ }
}
