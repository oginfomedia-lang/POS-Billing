"""Restoring a backup: the target database must exist (an installed shop's is literetailer_db, not pos_db), every
restore ends as one finished row, and rows left "running" by an interrupted restore are closed."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models.backup import BackupRun
from app.models.restore_record import RestoreRecord
from app.services import restore_service

pytestmark = pytest.mark.integration


@pytest.fixture
def backup(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "BACKUP_DIR", str(tmp_path))
    dump = tmp_path / "pos_20261021.pgdump"
    dump.write_bytes(b"PGDMP fake")
    run = BackupRun(filename=dump.name, file_path=str(dump), status="success")
    db.session.add(run)
    db.session.commit()
    return run


@pytest.fixture
def pg(monkeypatch):
    """Fake pg_dump / pg_restore: set .fail to the program name that should fail."""
    calls = SimpleNamespace(fail=None, programs=[])

    def run(cmd, **kwargs):
        program = "pg_dump" if "pg_dump" in cmd[0] else "pg_restore"
        calls.programs.append(program)
        if calls.fail == program:
            return SimpleNamespace(returncode=1, stderr=f"{program}: error: boom", stdout="")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(restore_service.subprocess, "run", run)
    return calls


def _restore(client, headers, backup_id, target):
    return client.post(f"/api/v1/backups/{backup_id}/restore", json={"target_db": target}, headers=headers)


def _rows():
    db.session.expire_all()
    return db.session.scalars(db.select(RestoreRecord)).all()


def test_unknown_database_is_refused_with_the_right_name(client, admin_headers, backup, pg):
    resp = _restore(client, admin_headers, backup.id, "pos_db_missing")
    assert resp.status_code == 400
    message = resp.get_json()["error"]["message"]
    assert 'Database "pos_db_missing" does not exist' in message
    assert f'"{restore_service.current_db_name()}"' in message
    assert _rows() == [] and pg.programs == []


def test_bad_database_name_is_refused(client, admin_headers, backup, pg):
    assert _restore(client, admin_headers, backup.id, "x; drop").status_code == 400
    assert _rows() == []


def test_failed_safety_dump_leaves_one_failed_row(client, admin_headers, backup, pg):
    pg.fail = "pg_dump"
    resp = _restore(client, admin_headers, backup.id, "postgres")
    assert resp.status_code == 201
    rows = _rows()
    assert [(r.status, r.target_db) for r in rows] == [("failed", "postgres")]
    assert "Safety pre-restore dump failed" in rows[0].error_message
    assert pg.programs == ["pg_dump"]


def test_restore_into_another_database_finishes_its_row(client, admin_headers, backup, pg):
    resp = _restore(client, admin_headers, backup.id, "postgres")
    assert resp.status_code == 201 and resp.get_json()["status"] == "success"
    rows = _rows()
    assert [r.status for r in rows] == ["success"] and rows[0].safety_backup_path
    assert pg.programs == ["pg_dump", "pg_restore"]


def test_restore_into_the_live_database_records_one_row(client, admin_headers, backup, pg):
    resp = _restore(client, admin_headers, backup.id, restore_service.current_db_name())
    assert resp.status_code == 201 and resp.get_json()["status"] == "success"
    assert [r.status for r in _rows()] == ["success"]


def test_failed_pg_restore_is_reported(client, admin_headers, backup, pg):
    pg.fail = "pg_restore"
    resp = _restore(client, admin_headers, backup.id, "postgres")
    assert resp.get_json()["status"] == "failed"
    assert "boom" in resp.get_json()["error_message"]
    assert len(_rows()) == 1


def test_stale_running_rows_are_closed_and_list_names_the_database(client, admin_headers):
    old = RestoreRecord(target_db="pos_db", status="running",
                        started_at=datetime.now(timezone.utc) - timedelta(hours=3))
    recent = RestoreRecord(target_db="pos_db", status="running", started_at=datetime.now(timezone.utc))
    db.session.add_all([old, recent])
    db.session.commit()

    body = client.get("/api/v1/backups/restores", headers=admin_headers).get_json()
    assert body["current_db"] == restore_service.current_db_name()
    status = {r["id"]: (r["status"], r["error_message"]) for r in body["items"]}
    assert status[old.id][0] == "failed" and "Interrupted" in status[old.id][1]
    assert status[recent.id] == ("running", None)
