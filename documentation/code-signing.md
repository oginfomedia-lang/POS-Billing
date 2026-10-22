# Code signing the installer

Unsigned, `LiteRetail-Setup-<version>.exe` makes Windows SmartScreen show "Windows protected your PC" and some
antivirus programs quarantine the frozen backend. A signed build shows **LiteCode Software Pvt Ltd** as the publisher.
Signed builds are also what auto-update checks: an update is installed only if it is signed by the same publisher
as the installed version (see [auto-update.md](auto-update.md)).

`scripts\build\build_installer.ps1` signs everything electron-builder packs: `LiteRetail.exe`, the installer,
the uninstaller, `literetailer-backend.exe` and the WinSW service exe. It then checks the signatures and stops if
any is missing. Without a certificate it builds unsigned and prints a warning; pass `-RequireSigning` for
release builds so that can't happen by accident.

## Getting a certificate

Since June 2023, certificate authorities only issue code-signing keys on hardware (USB token / HSM) or in a cloud
service. A plain `.pfx` file you can copy around is no longer sold. Choose one of the following.

| Option | Cost (approx.) | SmartScreen | Notes |
|---|---|---|---|
| **Azure Trusted Signing** (recommended if available to you) | ~US$10 / month | Reputation builds up quickly | Microsoft verifies the company. No hardware; works from any build PC. Public-trust signing has been open only to organisations in some countries: check that an Indian company is eligible before choosing it. |
| OV certificate on a USB token (Sectigo, DigiCert, …) | ~US$200–400 / year | Reputation builds up over downloads | The token must be plugged into the build PC (option C). |
| EV certificate on a token | ~US$300–600 / year | Trusted at once | Same token setup as OV. |

## Option A: Azure Trusted Signing

1. In the Azure portal create a *Trusted Signing account*, complete identity validation for LiteCode Software Pvt Ltd,
   and create a *certificate profile* (Public Trust).
2. Create an app registration (service principal) and give it the role **Trusted Signing Certificate Profile Signer**
   on the account.
3. On the build PC, before running the build:

```powershell
$env:AZURE_TENANT_ID           = '<tenant id>'
$env:AZURE_CLIENT_ID           = '<app registration client id>'
$env:AZURE_CLIENT_SECRET       = '<client secret>'
$env:LITERETAIL_SIGN_ENDPOINT  = 'https://<region>.codesigning.azure.net'   # shown on the account's overview page
$env:LITERETAIL_SIGN_ACCOUNT   = '<trusted signing account name>'
$env:LITERETAIL_SIGN_PROFILE   = '<certificate profile name>'
$env:LITERETAIL_SIGN_PUBLISHER = 'LiteCode Software Pvt Ltd'           # the certificate's subject CN
powershell -ExecutionPolicy Bypass -File scripts\build\build_installer.ps1 -RequireSigning
```

electron-builder installs the Trusted Signing PowerShell module itself the first time.

## Option B: a `.pfx` certificate

```powershell
$env:CSC_LINK         = 'C:\secure\litecode-codesign.pfx'
$env:CSC_KEY_PASSWORD = '<password>'
powershell -ExecutionPolicy Bypass -File scripts\build\build_installer.ps1 -RequireSigning
```

## Option C: a certificate on a USB token

Install the CA's token driver, plug the token in, and check that the certificate shows in
`certmgr.msc` → Personal → Certificates. Then:

```powershell
$env:LITERETAIL_SIGN_SUBJECT = 'LiteCode Software Pvt Ltd'   # the certificate's "Issued to" name
powershell -ExecutionPolicy Bypass -File scripts\build\build_installer.ps1 -RequireSigning
```

The token asks for its PIN while signing (several times: one per signed file).

## Keep in mind

- Never commit the certificate, its password or the Azure secret. Set them only in the build PC's session.
- Keep using the **same publisher name** for every release. Auto-update refuses an update signed by a different one.
- Check a build by hand: right-click the setup exe → Properties → Digital Signatures.
