// ESC/POS commands sent raw to the receipt printer.
// Only the drawer kick goes raw: receipts print as HTML so Marathi text uses Windows fonts
// (thermal printers' built-in character sets have no Devanagari).

/** ESC p m t1 t2 — pulse drawer pin m: on for t1×2 ms, off for t2×2 ms. */
export const DRAWER_KICK_PIN2 = [0x1b, 0x70, 0x00, 0x19, 0xfa];
/** Some drawers are wired to pin 5 instead; sending both opens either kind. */
export const DRAWER_KICK_PIN5 = [0x1b, 0x70, 0x01, 0x19, 0xfa];
