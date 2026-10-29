"""Backup files on the VPS: client uploads (CLIENT_BACKUP_DIR) can be downloaded and restored, backups left
"running" are closed, the restore state is shared between server processes, and a restore's safety copy appears in
the Backups list."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models.backup import BackupRun
from app.services import restore_service

pytestmark = pytest.mark.integration


@pytest.fixture
def dirs(app, tmp_path, monkeypatch):
    own, clients, elsewhere = tmp_path / "daily", tmp_path / "clients", tmp_path / "elsewhere"
    for d in (own, clients, elsewhere):
        d.mkdir()
    monkeypatch.setitem(app.config, "BACKUP_DIR", str(own))
    monkeypatch.setitem(app.config, "CLIENT_BACKUP_DIR", str(clients))
    return SimpleNamespace(own=own, clients=clients, elsewhere=elsewhere)


def _backup(folder, name, status="success", started_at=None):
    f = folder / name
    f.write_bytes(b"PGDMP fake")
    run = BackupRun(filename=name, file_path=str(f), status=status,
                    started_at=started_at or datetime.now(timezone.utc))
    db.session.add(run)
    db.session.commit()
    return run.id


def test_client_backup_downloads(client, admin_headers, dirs):
    backup_id = _backup(dirs.clients, "pos_aishwarya-15c9b3_20261029_050000.pgdump")
    resp = client.get(f"/api/v1/backups/{backup_id}/download", headers=admin_headers)
    assert resp.status_code == 200 and resp.data == b"PGDMP fake"


def test_file_outside_both_folders_is_refused(client, admin_headers, dirs):
    backup_id = _backup(dirs.elsewhere, "pos_x_20261029_050000.pgdump")
    resp = client.get(f"/api/v1/backups/{backup_id}/download", headers=admin_headers)
    assert resp.status_code == 400 and resp.get_json()["error"]["message"] == "Invalid backup file path."


def test_old_running_backup_is_closed(client, admin_headers, dirs):
    old = _backup(dirs.own, "old.pgdump", "running", datetime.now(timezone.utc) - timedelta(minutes=20))
    new = _backup(dirs.own, "new.pgdump", "running", datetime.now(timezone.utc) - timedelta(minutes=1))
    items = client.get("/api/v1/backups", headers=admin_headers).get_json()["items"]
    status = {b["id"]: (b["status"], b["error_message"]) for b in items}
    assert status[old][0] == "failed" and "Not finished" in status[old][1]
    assert status[new] == ("running", None)


def test_restore_state_of_a_dead_process_is_ignored(app, dirs):
    with app.app_context():
        restore_service._state_file().write_text(json.dumps({
            "active": {"id": 1, "live": True, "pid": 2 ** 22 + 12345}, "last": None}))
        assert restore_service._shared() == (None, None)
        assert not restore_service.live_restore_running()


def test_safety_copy_is_listed_after_a_restore(client, admin_headers, dirs, monkeypatch):
    def run(cmd, **kwargs):
        if "pg_dump" in cmd[0]:
            Path(cmd[cmd.index("-f") + 1]).write_bytes(b"PGDMP safety")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(restore_service.subprocess, "run", run)
    monkeypatch.setattr(restore_service, "_end_other_connections", lambda target: None)
    backup_id = _backup(dirs.clients, "pos_aishwarya-15c9b3_20261029_050000.pgdump")  # a client's backup restores
    resp = client.post(f"/api/v1/backups/{backup_id}/restore", json={"target_db": "postgres"}, headers=admin_headers)
    assert resp.status_code == 202
    restore_service.wait(10)

    db.session.expire_all()
    safety = db.session.scalars(db.select(BackupRun).where(BackupRun.filename.like("safety_postgres_%"))).all()
    assert [s.status for s in safety] == ["success"] and safety[0].checksum_sha256
