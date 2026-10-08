// Opens the cash drawer through the receipt printer (the drawer cable plugs into the printer's RJ11 port).
import type { CounterConfig } from '../config/counterConfig';
import { DRAWER_KICK_PIN2, DRAWER_KICK_PIN5 } from './printer/escpos';
import { sendRaw } from './printer/thermalPrinter';

/** Does nothing when the drawer is switched off for this counter. */
export async function openDrawer(config: CounterConfig): Promise<void> {
  if (!config.drawerEnabled) return;
  await sendRaw(config.printerName, [...DRAWER_KICK_PIN2, ...DRAWER_KICK_PIN5]);
}
