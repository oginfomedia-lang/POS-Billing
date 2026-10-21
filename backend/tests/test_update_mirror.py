"""The Main PC copies new installers from UPDATE_FEED_URL and serves them to the apps at /api/v1/updates."""
import base64
import hashlib

import pytest

from app.services import update_mirror_service

FEED = "https://updates.example.test/literetail"


def _latest(version: str, data: bytes, name: str | None = None, sha: str | None = None) -> str:
    name = name or f"LiteRetail-Setup-{version}.exe"
    sha = sha or base64.b64encode(hashlib.sha512(data).digest()).decode()
    return (
        f"version: {version}\nfiles:\n  - url: {name}\n    sha512: {sha}\n    size: {len(data)}\n"
        f"path: {name}\nsha512: {sha}\nreleaseDate: '2026-10-21T10:00:00.000Z'\n"
    )


class FakeFeed:
    """Stands in for requests.get against the vendor's update folder."""

    def __init__(self, files: dict[str, bytes | str]):
        self.files = files
        self.requested: list[str] = []

    def get(self, url, stream=False, timeout=None):
        self.requested.append(url)
        return _Resp(self.files.get(url.removeprefix(FEED + "/")))


class _Resp:
    def __init__(self, body):
        self.body = body
        self.status_code = 404 if body is None else 200

    @property
    def text(self):
        return self.body if isinstance(self.body, str) else self.body.decode()

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        data = self.body.encode() if isinstance(self.body, str) else self.body
        yield from (data[i:i + chunk_size] for i in range(0, len(data), chunk_size))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def mirror(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "UPDATE_FEED_URL", FEED)
    monkeypatch.setitem(app.config, "UPDATE_DIR", str(tmp_path))

    def install(files):
        feed = FakeFeed(files)
        monkeypatch.setattr(update_mirror_service.requests, "get", feed.get)
        return feed
    return install


def test_new_version_is_copied_and_served(client, mirror, tmp_path):
    exe = b"MZ fake installer 1.0.1" * 1000
    mirror({"latest.yml": _latest("1.0.1", exe), "LiteRetail-Setup-1.0.1.exe": exe,
            "LiteRetail-Setup-1.0.1.exe.blockmap": b"blockmap"})
    assert update_mirror_service.sync() == "1.0.1"

    latest = client.get("/api/v1/updates/latest.yml")
    assert latest.status_code == 200 and "version: 1.0.1" in latest.get_data(as_text=True)
    assert client.get("/api/v1/updates/LiteRetail-Setup-1.0.1.exe").data == exe
    assert client.get("/api/v1/updates/LiteRetail-Setup-1.0.1.exe.blockmap").status_code == 200
    assert update_mirror_service.status()["error"] is None


def test_same_version_is_not_downloaded_again(mirror):
    exe = b"installer"
    feed = mirror({"latest.yml": _latest("1.0.1", exe), "LiteRetail-Setup-1.0.1.exe": exe})
    update_mirror_service.sync()
    feed.requested.clear()
    update_mirror_service.sync()
    assert feed.requested == [f"{FEED}/latest.yml"]


def test_corrupt_download_keeps_the_old_version(client, mirror):
    old = b"old installer"
    mirror({"latest.yml": _latest("1.0.1", old), "LiteRetail-Setup-1.0.1.exe": old})
    update_mirror_service.sync()

    new = b"new installer"
    mirror({"latest.yml": _latest("1.0.2", new, sha=base64.b64encode(b"x" * 64).decode()),
            "LiteRetail-Setup-1.0.2.exe": new})
    assert update_mirror_service.sync() == "1.0.1"
    assert "SHA-512" in update_mirror_service.status()["error"]
    assert "version: 1.0.1" in client.get("/api/v1/updates/latest.yml").get_data(as_text=True)
    assert client.get("/api/v1/updates/LiteRetail-Setup-1.0.2.exe").status_code == 404


def test_old_installer_is_removed_after_an_update(client, mirror, tmp_path):
    a, b = b"one", b"two"
    mirror({"latest.yml": _latest("1.0.1", a), "LiteRetail-Setup-1.0.1.exe": a})
    update_mirror_service.sync()
    mirror({"latest.yml": _latest("1.0.2", b), "LiteRetail-Setup-1.0.2.exe": b})
    update_mirror_service.sync()
    assert not (tmp_path / "LiteRetail-Setup-1.0.1.exe").exists()
    assert client.get("/api/v1/updates/LiteRetail-Setup-1.0.2.exe").data == b"two"


def test_latest_yml_cannot_point_outside_the_folder(mirror):
    mirror({"latest.yml": _latest("9.9.9", b"x", name="..\\..\\evil.exe")})
    assert update_mirror_service.sync() is None
    assert "unexpected file" in update_mirror_service.status()["error"]


def test_only_update_files_are_served(client, mirror, tmp_path):
    (tmp_path / "status.json").write_text("{}")
    assert client.get("/api/v1/updates/status.json").status_code == 404
    assert client.get("/api/v1/updates/..%2Fbackend.env").status_code == 404


def test_no_feed_means_no_check(app, monkeypatch):
    monkeypatch.setitem(app.config, "UPDATE_FEED_URL", "")
    assert update_mirror_service.sync() is None


def test_update_files_skip_the_licence_check(client, mirror, monkeypatch, app):
    monkeypatch.setitem(app.config, "LICENSE_REQUIRED", True)
    exe = b"installer"
    mirror({"latest.yml": _latest("1.0.1", exe), "LiteRetail-Setup-1.0.1.exe": exe})
    update_mirror_service.sync()
    assert client.get("/api/v1/updates/latest.yml").status_code == 200
