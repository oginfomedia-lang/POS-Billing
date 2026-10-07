// Makes t('…') type-checked: a misspelt or missing key is a TypeScript error.
import 'i18next';
import type { Messages } from './locales/en';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: { translation: Messages };
  }
}
