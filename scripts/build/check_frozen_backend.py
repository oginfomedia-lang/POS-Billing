"""Every module under backend/app must be inside the frozen backend. Run from backend/ after PyInstaller
(scripts/build/build_installer.ps1 does). Exit 1 and the missing names when something was left out: a module nothing
imports (e.g. one used only by migrations) would otherwise only fail on the client."""
import pathlib
import sys

from PyInstaller.archive.readers import ZlibArchiveReader

pyz = next(pathlib.Path("build/literetailer-backend").glob("PYZ-*.pyz"))
frozen = set(ZlibArchiveReader(str(pyz)).toc)
wanted = {".".join(p.with_suffix("").parts).removesuffix(".__init__") for p in pathlib.Path("app").rglob("*.py")}
missing = sorted(wanted - frozen)
if missing:
    print("Missing from the frozen backend: " + ", ".join(missing))
    sys.exit(1)
print(f"All {len(wanted)} backend modules are in the frozen backend.")
