// Exposes the safe window.posBridge API to React.
// React never gets Node.js or hardware access directly; only these functions.
import { contextBridge, ipcRenderer } from 'electron';
import type { CounterConfig } from './config/counterConfig';
import { IPC } from './ipc/channels';

const posBridge = {
  getCounterConfig: (): Promise<CounterConfig> => ipcRenderer.invoke(IPC.getCounterConfig),
};

export type PosBridge = typeof posBridge;

contextBridge.exposeInMainWorld('posBridge', posBridge);
