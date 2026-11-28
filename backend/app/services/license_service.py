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

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_der_public_key
from flask import current_app

from app.errors.exceptions import PlanLimitError
from app.utils.paths import data_dir

# v1 keys (HMAC). This secret has leaked, so v1 keys are accepted only until every shop has a v2 key;
# then a release sets ACCEPT_V1_KEYS = False. Changing SECRET invalidates every v1 key.
SECRET = b"69c2713fd5fb902bd0d22a33b7ccc958a22ab921f0ee66a50d1ca045fcf5ab54"
ACCEPT_V1_KEYS = True

# v2 keys (Ed25519). Only the licence server has the private key: this app can check keys, never make them.
PUBLIC_KEY_B64 = "MCowBQYDK2VwAyEAFpfVXhQ1O404Rq8qKRXUtoqvroSelsiVsHuX8ZPEbkE="

# Features a plan switches on. Billing, products, inventory, basic reports and local backup are in every plan.
ALL_FEATURES = frozenset({
    "customers", "discounts", "card_upi", "ebill_whatsapp", "weighing_scale", "labels",
    "purchases", "audit_logs", "accounting", "price_review", "daily_report", "cloud_backup",
})

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
    plan: str | None = None                    # starter | business | enterprise (v1 keys: enterprise)
    features: frozenset[str] = frozenset()
    limits: dict | None = None                 # {"counters": 2, "stores": 1, "users": 3}; missing = unlimited
    amc_until: str | None = None               # updates and support until this date (billing never stops)
    key_version: int | None = None

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "machine_id": self.machine_id,
            "reason": self.reason,
            "expires_at": self.expires_at,
            "days_left": self.days_left,
            "customer_name": self.customer_name,
            "plan": self.plan,
            "features": sorted(self.features),
            "limits": self.limits or {},
            "amc_until": self.amc_until,
            "key_version": self.key_version,
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


def _b64url_bytes(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _v1_signature_ok(payload_b64: str, sig: str) -> bool:
    expected = hmac.new(SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig.encode(), expected.encode())


def _v2_signature_ok(payload_b64: str, sig: str) -> bool:
    try:
        load_der_public_key(base64.b64decode(PUBLIC_KEY_B64)).verify(_b64url_bytes(sig), payload_b64.encode())
        return True
    except (InvalidSignature, ValueError):
        return False


def _parse_dt(value) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def validate(key: str) -> LicenseStatus:
    """v1 key: 32-hex HMAC signature, every feature (sold before plans). v2 key: Ed25519 signature,
    features and limits from its plan, `exp` null = perpetual."""
    mid = machine_id()
    if not key:
        return LicenseStatus(False, mid, "not_activated")
    payload_b64, dot, sig = key.rpartition(".")
    if not dot or not payload_b64:
        return LicenseStatus(False, mid, "invalid_key")

    if len(sig) == 32:
        version, signed = 1, ACCEPT_V1_KEYS and _v1_signature_ok(payload_b64, sig)
    else:
        version, signed = 2, _v2_signature_ok(payload_b64, sig)
    if not signed:
        return LicenseStatus(False, mid, "invalid_key")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
        exp = payload.get("exp") if version == 2 else payload["exp"]
        expires = _parse_dt(exp) if exp else None
    except (ValueError, KeyError, TypeError, AttributeError):
        return LicenseStatus(False, mid, "invalid_key")

    if payload.get("mid") != mid:
        return LicenseStatus(False, mid, "wrong_machine")
    days_left = None
    if expires is not None:
        seconds_left = (expires - datetime.now(timezone.utc)).total_seconds()
        if seconds_left < 0:
            return LicenseStatus(False, mid, "expired", expires_at=exp)
        days_left = int(-(-seconds_left // 86400))

    if version == 1:
        plan, features, limits = "enterprise", ALL_FEATURES, None
    else:
        plan = payload.get("plan")
        features = frozenset(payload.get("features") or ()) & ALL_FEATURES
        limits = payload.get("limits") if isinstance(payload.get("limits"), dict) else None
    return LicenseStatus(True, mid, expires_at=exp, days_left=days_left, customer_name=payload.get("customer"),
                         plan=plan, features=features, limits=limits, amc_until=payload.get("amc_until"),
                         key_version=version)


def current_status(use_cache: bool = True) -> LicenseStatus:
    """Status of the saved key (cached for a minute: it is checked on every API request)."""
    global _cache
    now = time.monotonic()
    if use_cache and _cache and now - _cache[0] < _CACHE_SECONDS:
        return _cache[1]
    status = validate(_read_key())
    _cache = (now, status)
    return status


def has_feature(name: str) -> bool:
    return name in current_status().features


def allows(name: str) -> bool:
    """Can this shop use `name`? Always yes when licences aren't enforced (development, tests)."""
    return not current_app.config.get("LICENSE_REQUIRED") or has_feature(name)


def limit(name: str) -> int | None:
    """The plan's cap on counters / stores / users. None = unlimited."""
    value = (current_status().limits or {}).get(name)
    return None if value is None else int(value)


def check_limit(name: str, in_use: int) -> None:
    """Raises PlanLimitError if adding one more `name` (stores / users) would go past the plan's cap.
    Only when licences are enforced (LICENSE_REQUIRED): development and the installer's setup are not capped."""
    if not current_app.config.get("LICENSE_REQUIRED"):
        return
    cap = limit(name)
    if cap is not None and in_use >= cap:
        raise PlanLimitError(f"Your LiteRetail plan allows {cap} {name}. Upgrade the plan to add more.",
                             {"limit": name, "allowed": cap})


def check_counter_allowed(counter_id: int) -> None:
    """The installer adds counters C01-C05 whatever the plan, so the cap is checked when a shift opens:
    only the plan's first N active counters (oldest first) can bill."""
    if not current_app.config.get("LICENSE_REQUIRED"):
        return
    cap = limit("counters")
    if cap is None:
        return
    from app.models.store import Counter

    allowed = [c.id for c in Counter.query.filter_by(is_active=True).order_by(Counter.id).limit(cap)]
    if counter_id not in allowed:
        raise PlanLimitError(f"Your LiteRetail plan allows {cap} counter(s). Use one of the first {cap} "
                             "counters, or upgrade the plan.", {"limit": "counters", "allowed": cap})


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
