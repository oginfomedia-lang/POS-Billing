// UI translations (English / Marathi). Both languages are bundled, so it works offline on the till.
// The chosen language is remembered per till in localStorage.
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { en } from './locales/en';
import { mr } from './locales/mr';

export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'mr', label: 'मराठी' },
] as const;

export type LanguageCode = (typeof LANGUAGES)[number]['code'];

const STORAGE_KEY = 'pos-language';

function savedLanguage(): LanguageCode {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'mr' ? 'mr' : 'en';
  } catch {
    return 'en';
  }
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, mr: { translation: mr } },
  lng: savedLanguage(),
  fallbackLng: 'en', // a missing Marathi text shows English instead of a raw key
  interpolation: { escapeValue: false }, // React already escapes what it renders
});

function applyLanguage(lng: string) {
  document.documentElement.lang = lng; // lets the browser pick Devanagari fonts and hyphenation
}

i18n.on('languageChanged', (lng) => {
  try { localStorage.setItem(STORAGE_KEY, lng); } catch { /* storage unavailable */ }
  applyLanguage(lng);
});
applyLanguage(i18n.language);

/**
 * Locale for dates: Marathi month/day names, but Latin digits (0–9), which is what
 * tills, receipts and staff use. Money keeps en-IN formatting (₹1,00,000.00) in both languages.
 */
export function intlLocale(): string {
  return i18n.language === 'mr' ? 'mr-IN-u-nu-latn' : 'en-IN';
}

export default i18n;
