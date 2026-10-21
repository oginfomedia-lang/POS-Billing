# Offline billing

When a counter can't reach the Main PC (network cable out, Main PC off), the cashier can keep taking **cash**
bills. They are saved on the counter and sent to the server by themselves when it is back.

## For the cashier

- The billing screen shows **The server cannot be reached** with a **Bill offline (cash)** button. If the app was
  restarted during the outage, the same button is on the "Cannot reach the LiteRetail server" screen.
- Scan as usual (barcodes, SKUs and weighing-scale stickers work), or type part of a name. Offers apply as usual.
- **F12** takes the cash, then the bill is saved, printed and the drawer opens. Offline bill numbers look like
  `C02-OFF-261021-0001` (counter, `OFF`, date, number).
- The status bar shows *N offline bills waiting to upload* until they are sent. When the server is back, finish the
  current bill and click **Go to normal billing**.

Not available offline: card / UPI, customer mobile and reward points, returns, held bills, manager discounts,
opening or closing a shift.

## What it needs

- A shift **opened on this PC** while the server was up, by the cashier who is still logged in. Offline billing
  can't start a shift.
- The product list on this PC. It downloads every 5 minutes while the server is up (products, this store's
  prices, offers, receipt header/footer). The offline screen shows how old it is.
- After an app restart: the shop licence must have been confirmed in the last 7 days.

## How it works (support)

| Part | Where |
|---|---|
| Product list and offers | `GET /api/v1/pos/offline-catalog?store_id=` → `%APPDATA%\LiteRetail\offline\catalog-<store>.json` |
| Saved bills | `%APPDATA%\LiteRetail\offline\queue\` until uploaded, then `offline\synced\` (kept 30 days) |
| Pricing | `frontend/src/offline/pricing.ts`, the same rules as the server; a shared test fixture checks they agree |
| Upload | `POST /api/v1/sales/offline`, every minute while the server is up (sending a bill twice records it once) |

On upload the server records the bill **exactly as the customer paid**. It recomputes each line's GST and the total
from the amounts sent and refuses the bill if they don't add up, but it doesn't re-apply offers (they may have
changed). Stock is taken off as usual. If the records had less stock than was sold offline, stock goes to 0 and the
shortfall is noted on the stock ledger and in the audit log (`sale.offline`) for the manager to check.

A bill the server refuses stays on the counter with the reason, shown on the offline screen with a **Try again**
button. Bills belong to their cashier: a waiting bill is uploaded when that cashier is logged in on that counter.
