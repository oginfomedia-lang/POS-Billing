// Type declarations for window.posBridge (defined in electron/preload.ts).
import type { PosBridge } from '../../electron/preload';

declare global {
  interface Window {
    posBridge: PosBridge;
  }
}

export {};
