"""Keeps a copy of the newest LiteRetail installer on the Main PC, for every PC's app to update from.

The vendor publishes electron-builder's output (latest.yml, LiteRetail-Setup-<version>.exe and its .blockmap) to
UPDATE_FEED_URL. sync() runs on the scheduler: when latest.yml names a version not copied yet, it downloads the
installer, checks it against the SHA-512 in latest.yml, and only then puts latest.yml in place. So the apps
(electron-updater, generic provider at <apiUrl>/updates) never see a version whose files are incomplete.
Counter PCs therefore update over the store LAN, without internet.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import current_app

from app.utils.paths import data_dir

logger = logging.getLogger(__name__)

TIMEOUT = 30  # seconds per request; the installer itself streams for as long as it takes
LATEST = "latest.yml"
STATUS = "status.json"
# Only these names are ever written or served (no paths: latest.yml can't make us write elsewhere).
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\.(exe|blockmap)$")


def updates_dir() -> Path:
    path = Path(current_app.config.get("UPDATE_DIR") or data_dir() / "updates")
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_latest(text: str) -> dict:
    """version / path / sha512 from electron-builder's latest.yml (top-level keys only; no YAML library needed)."""
    out = {}
    for key in ("version", "path", "sha512"):
        m = re.search(rf"^{key}:\s*['\"]?([^'\"\r\n]+?)['\"]?\s*$", text, re.MULTILINE)
        if m:
            out[key] = m.group(1)
    if set(out) != {"version", "path", "sha512"}:
        raise ValueError("latest.yml is missing version, path or sha512.")
    if not SAFE_NAME.match(out["path"]):
        raise ValueError(f"latest.yml names an unexpected file: {out['path']!r}")
    return out


def status() -> dict:
    """What the mirror holds now and how the last check went."""
    try:
        return json.loads((updates_dir() / STATUS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": None, "checked_at": None, "error": None}


def sync() -> str | None:
    """Copies a new version if the feed has one. Returns the version now served (None = nothing yet)."""
    feed = (current_app.config.get("UPDATE_FEED_URL") or "").rstrip("/")
    if not feed:
        return None
    folder = updates_dir()
    state = status()
    try:
        resp = requests.get(f"{feed}/{LATEST}", timeout=TIMEOUT)
        resp.raise_for_status()
        latest_text = resp.text
        latest = parse_latest(latest_text)
        if latest["version"] != state.get("version") or not (folder / latest["path"]).exists():
            _download(f"{feed}/{latest['path']}", folder / latest["path"], latest["sha512"])
            _download(f"{feed}/{latest['path']}.blockmap", folder / f"{latest['path']}.blockmap", None, optional=True)
            _replace(folder / LATEST, latest_text.encode("utf-8"))  # last: the version is complete now
            _remove_old(folder, keep={LATEST, STATUS, latest["path"], f"{latest['path']}.blockmap"})
            logger.info("Update %s copied from %s", latest["version"], feed)
        state = {"version": latest["version"], "error": None}
    except Exception as exc:  # noqa: BLE001 - a failed check is retried next time; the old copy stays served
        logger.warning("Update check failed: %s", exc)
        state = {"version": state.get("version"), "error": str(exc)}
    state["checked_at"] = datetime.now(timezone.utc).isoformat()
    _replace(folder / STATUS, json.dumps(state).encode("utf-8"))
    return state["version"]


def _download(url: str, dest: Path, sha512_b64: str | None, optional: bool = False) -> None:
    part = dest.with_name(dest.name + ".part")
    digest = hashlib.sha512()
    with requests.get(url, stream=True, timeout=TIMEOUT) as resp:
        if optional and resp.status_code == 404:
            return
        resp.raise_for_status()
        with part.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                digest.update(chunk)
    if sha512_b64 is not None and base64.b64encode(digest.digest()).decode() != sha512_b64:
        part.unlink(missing_ok=True)
        raise ValueError(f"{dest.name}: downloaded file does not match the SHA-512 in latest.yml.")
    os.replace(part, dest)


def _replace(dest: Path, data: bytes) -> None:
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)


def _remove_old(folder: Path, keep: set[str]) -> None:
    for f in folder.iterdir():
        if f.is_file() and f.name not in keep:
            f.unlink(missing_ok=True)
