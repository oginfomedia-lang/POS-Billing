# Hardware setup: scanner, receipt printer, cash drawer

One counter PC = one POS app, one barcode scanner, one 80 mm receipt printer, one cash drawer.

## Barcode scanner

Any USB scanner in **keyboard (HID) mode** works. It types the barcode and presses Enter. No setup in the app.

## Receipt printer (80 mm thermal)

1. Install the printer's **Windows driver** from the maker's website (TVS, Epson TM, Posiflex, Rugtek…).
   The printer must show up in *Windows Settings → Bluetooth & devices → Printers & scanners*.
2. In the printer's driver settings, set the paper to **80 mm (72 mm printable) roll**, with no margins.
3. In the POS app, log in as a manager or admin and open **Settings → This counter's printer**:
   - **Receipt printer**: pick the printer. "Windows default printer" also works if it is the default.
   - **Print the receipt automatically**: on for normal use.
   - Click **Save printer settings**, then **Test print**. A small "PRINTER TEST" slip should come
     out with Marathi letters (अ आ इ ई) printed correctly.

These settings are saved on **this PC only**, in `%APPDATA%\pos-billing-frontend\counter.json`
(`printerName`, `autoPrint`, `drawerEnabled`), so every counter can use its own printer.

How it works: the receipt is printed by Windows, the same as from any program, but without the print
dialog. Windows fonts are used, so Marathi product names and labels print correctly.
(Thermal printers' own character sets have no Devanagari, so sending raw text would not work.)

## Cash drawer

1. Plug the drawer cable into the printer's **DK / RJ11 "drawer" port**, not into the PC.
2. In **Settings → This counter's printer**, tick **Open the cash drawer on cash sales and cash refunds**,
   save, and click **Open drawer**. The drawer should pop open.
3. The drawer then opens by itself:
   - after a **cash** sale (not card/UPI);
   - after a **return** (refunds are always cash).

How it works: the app sends the standard ESC/POS "kick" command (`ESC p`) to the printer through
Windows (hidden PowerShell + the Windows print spooler). The first time takes a few seconds while
a small helper is prepared (`pos-raw-printer-v1.dll` next to `counter.json`); after that it takes
under a second.

## Troubleshooting

| Problem | What to check |
|---|---|
| "Could not print: …" banner on the receipt | Printer is on, has paper, isn't offline in Windows. Click **Print** to try again. |
| Receipt prints very small / with big margins | Paper size in the printer **driver** (80 mm roll, no margins). |
| Receipt prints on the wrong printer | Settings → This counter's printer → pick the right one → Save. |
| Drawer doesn't open, message "Printer not found: …" | The printer was renamed in Windows: pick it again in Settings and save. |
| Drawer doesn't open, no error | Cable in the printer's drawer port. Some drawers need the other pin; the app sends both pin 2 and pin 5. Check the drawer's key lock. |
| Want to stop auto-printing (e.g. to save paper while testing) | Untick **Print the receipt automatically**. The Print button still works. |
