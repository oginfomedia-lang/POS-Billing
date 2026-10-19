"""Shop licence: one key per shop, tied to the Main PC (the PC running this server).

Every PC in the store (Main PC and counters) asks this server through GET /license, so the shop is
activated once. The key format is the one the licence tool already issues:

    base64url(JSON payload) + "." + first 32 hex chars of HMAC-SHA256(payload_b64, SECRET)
    payload = {"product", "customer", "mid", "iat", "exp"}

`mid` is the Main PC's machine ID - the same fingerprint the Electron app used, so existing keys for
a Main PC stay valid. The key is saved in %ProgramData%\\LiteRetailer\\license.json.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import platform
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.utils.paths import data_dir

# Must match the licence tool. Changing it invalidates every issued key.
SECRET = b"69c2713fd5fb902bd0d22a33b7ccc958a22ab921f0ee66a50d1ca045fcf5ab54"

# Node's os.arch() names, so the fingerprint equals the one the Electron app showed.
_NODE_ARCH = {"AMD64": "x64", "x86_64": "x64", "ARM64": "arm64", "aarch64": "arm64", "x86": "ia32", "i386": "ia32"}

_CACHE_SECONDS = 60
_cache: tuple[float, "LicenseStatus"] | None = None


@dataclass(frozen=True)
class LicenseStatus:
    valid: bool
    machine_id: str
    reason: str | None = None          # not_activated | invalid_key | wrong_machine | expired
    expires_at: str | None = None
    days_left: int | None = None
    customer_name: str | None = None

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "machine_id": self.machine_id,
            "reason": self.reason,
            "expires_at": self.expires_at,
            "days_left": self.days_left,
            "customer_name": self.customer_name,
        }


def machine_id() -> str:
    """16-char fingerprint of this PC: sha256(hostname + platform + arch), Node.js naming."""
    arch = _NODE_ARCH.get(platform.machine(), platform.machine().lower())
    return hashlib.sha256((socket.gethostname() + sys.platform + arch).encode()).hexdigest()[:16]


def _license_path():
    return data_dir() / "license.json"


def _read_key() -> str:
    try:
        return (json.loads(_license_path().read_text(encoding="utf-8")).get("key") or "").strip()
    except (OSError, ValueError, AttributeError):
        return ""


def _b64url_decode(s: str) -> str:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8")


def validate(key: str) -> LicenseStatus:
    mid = machine_id()
    if not key:
        return LicenseStatus(False, mid, "not_activated")
    payload_b64, dot, sig = key.rpartition(".")
    if not dot:
        return LicenseStatus(False, mid, "invalid_key")

    expected = hmac.new(SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return LicenseStatus(False, mid, "invalid_key")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
        expires = datetime.fromisoformat(str(payload["exp"]).replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError):
        return LicenseStatus(False, mid, "invalid_key")

    if payload.get("mid") != mid:
        return LicenseStatus(False, mid, "wrong_machine")
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    seconds_left = (expires - datetime.now(timezone.utc)).total_seconds()
    if seconds_left < 0:
        return LicenseStatus(False, mid, "expired", expires_at=payload["exp"])
    return LicenseStatus(True, mid, expires_at=payload["exp"], days_left=int(-(-seconds_left // 86400)),
                         customer_name=payload.get("customer"))


def current_status(use_cache: bool = True) -> LicenseStatus:
    """Status of the saved key (cached for a minute: it is checked on every API request)."""
    global _cache
    now = time.monotonic()
    if use_cache and _cache and now - _cache[0] < _CACHE_SECONDS:
        return _cache[1]
    status = validate(_read_key())
    _cache = (now, status)
    return status


def activate(key: str) -> LicenseStatus:
    """Validates `key` and, if it is good, saves it for the whole shop."""
    global _cache
    status = validate(key.strip())
    if status.valid:
        path = _license_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"key": key.strip()}, indent=2), encoding="utf-8")
        _cache = None
    return status
