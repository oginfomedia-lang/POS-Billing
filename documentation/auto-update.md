# Automatic updates

New versions reach every shop without a visit. The Main PC fetches them from LiteCode's update folder, and every
PC in the shop (Main PC and counters) updates from the Main PC over the store network. Counters need no internet.

```text
LiteCode update folder (HTTPS)  ──every 6 h──>  Main PC server  ──LAN──>  LiteRetail app on each PC
  latest.yml                                   %ProgramData%\LiteRetailer\updates
  LiteRetail-Setup-1.2.0.exe                   served at http://<Main PC>:5000/api/v1/updates/
  LiteRetail-Setup-1.2.0.exe.blockmap
```

## How it works

1. **Main PC server** (`backend/app/services/update_mirror_service.py`). Every `UPDATE_CHECK_HOURS` (default 6,
   first check 3 minutes after start) it reads `latest.yml` from `UPDATE_FEED_URL`. When that names a new version,
   it downloads the installer and checks it against the SHA-512 in `latest.yml`. Only then does it put the new
   `latest.yml` in place, so an app never sees a half-downloaded version. A failed download keeps serving the
   previous version and is retried at the next check. Status: `GET /api/v1/updates-status` (admin / manager).
2. **Each app** (`frontend/electron/updater.ts`). One minute after start, then every 2 hours, the app asks
   `<apiUrl from counter.json>/updates/latest.yml`. A newer version downloads in the background.
   The status bar then says *Version x.y.z is ready* with a **Restart & update now** button. If nobody clicks it,
   the update installs when the app is closed at the end of the day.
3. **The installer** runs silently. On the Main PC it stops the LiteRetail Server service, brings the database up
   to the new version (`literetailer-backend seed`: migrations only, nothing else changes) and starts the service
   again. The result is in `%ProgramData%\LiteRetailer\logs\update.log`. Counters just get the new app.

Windows asks for administrator permission (UAC) when the update installs, because LiteRetail is installed for all
users under Program Files.

## Setting it up

1. Choose an HTTPS folder you control, e.g. `https://updates.litecode.in/literetail/`. Use HTTPS: the Main PC
   trusts whatever `latest.yml` it reads there.
2. Put its address in `UPDATE_FEED_URL`: in `backend/backend.env.template` (or `backend/backend.secrets.env`)
   before building, so every new installation gets it. On an already-installed Main PC, edit
   `C:\ProgramData\LiteRetailer\backend.env` and restart the LiteRetail Server service.
3. Shops installed before this version have no updater yet. Install this version on their PCs once, by hand.

## Releasing a new version

1. Raise `version` in `frontend/package.json` (e.g. `1.2.0`). Apps only update to a **higher** version.
2. Build a signed installer: `scripts\build\build_installer.ps1 -RequireSigning` (see [code-signing.md](code-signing.md)).
3. Upload these three files from `frontend\release\` to the update folder. Upload `latest.yml` **last**:

   - `LiteRetail-Setup-1.2.0.exe`
   - `LiteRetail-Setup-1.2.0.exe.blockmap` (lets apps download only the changed parts)
   - `latest.yml`

Within about 6 hours every Main PC has the new version. Each app picks it up within 2 hours of that and installs
it at the next close (or straight away with the button).

To stop a bad release, put the previous version's three files back. Apps that already installed the bad version
stay on it until a higher version is published, so release a fixed version with a higher number instead.

## Signing and updates

electron-updater checks that a downloaded installer is signed by the same publisher as the installed app. If the
installed app was signed, later updates must be signed with a certificate with the same publisher name. Unsigned
installations accept unsigned updates. Sign every release (see [code-signing.md](code-signing.md)).
