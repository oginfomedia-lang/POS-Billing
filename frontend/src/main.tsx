// React entry point.
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './i18n'; // must load before any screen renders
import '@fontsource-variable/noto-sans-devanagari';
import '@fontsource-variable/plus-jakarta-sans';
import '@fontsource/jetbrains-mono/500.css';
import '@fontsource/jetbrains-mono/700.css';
import './styles/global.css';
import { installNumberInputGuards } from './utils/numberInputs';

installNumberInputGuards();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
