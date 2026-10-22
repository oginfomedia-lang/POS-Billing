"""Restoring a backup: the target database must exist (an installed shop's is literetailer_db, not pos_db), it runs
in the background one at a time, every restore ends as one finished row, and rows left "running" by an interrupted
restore are closed."""
import threading
from datetime import datetime, timezone
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
    """Fake pg_dump / pg_restore: set .fail to the program name that should fail, .hold to an Event pg_restore
    waits for. Connections are not really closed and the schema is not upgraded."""
    calls = SimpleNamespace(fail=None, hold=None, programs=[], cmds=[], closed=[], upgraded=0)

    def run(cmd, **kwargs):
        program = "pg_dump" if "pg_dump" in cmd[0] else "pg_restore"
        calls.programs.append(program)
        calls.cmds.append(cmd)
        if program == "pg_restore" and calls.hold is not None:
            calls.hold.wait(10)
        if calls.fail == program:
            return SimpleNamespace(returncode=1, stderr=f"{program}: error: boom", stdout="")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    def upgraded():
        calls.upgraded += 1

    monkeypatch.setattr(restore_service.subprocess, "run", run)
    monkeypatch.setattr(restore_service, "_end_other_connections", calls.closed.append)
    monkeypatch.setattr(restore_service, "_upgrade_schema", upgraded)
    yield calls
    if calls.hold is not None:
        calls.hold.set()
    restore_service.wait(10)


def _restore(client, headers, backup_id, target, wait=True):
    resp = client.post(f"/api/v1/backups/{backup_id}/restore", json={"target_db": target}, headers=headers)
    if wait:
        restore_service.wait(10)
    return resp


def _finished(client, headers, resp):
    """The restore's row once it has finished (the POST answers while it is still running)."""
    assert resp.status_code == 202 and resp.get_json()["status"] == "running"
    return client.get("/api/v1/backups/restores", headers=headers).get_json()["items"][0]


def _rows():
    db.session.expire_all()
    return db.session.scalars(db.select(RestoreRecord)).all()


def _until(condition):
    for _ in range(200):
        if condition():
            return
        threading.Event().wait(0.05)
    raise AssertionError("timed out")


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
    assert _restore(client, admin_headers, backup.id, "postgres").status_code == 202
    rows = _rows()
    assert [(r.status, r.target_db) for r in rows] == [("failed", "postgres")]
    assert "Safety pre-restore dump failed" in rows[0].error_message
    assert pg.programs == ["pg_dump"]


def test_restore_into_another_database_finishes_its_row(client, admin_headers, backup, pg):
    resp = _restore(client, admin_headers, backup.id, "postgres")
    assert _finished(client, admin_headers, resp)["status"] == "success"
    rows = _rows()
    assert [r.status for r in rows] == ["success"] and rows[0].safety_backup_path
    assert pg.programs == ["pg_dump", "pg_restore"]
    assert "--single-transaction" in pg.cmds[1] and "--no-owner" in pg.cmds[1]
    assert pg.closed == ["postgres"] and pg.upgraded == 0  # another database: this server's layout is not touched


def test_restore_into_the_live_database_records_one_row(client, admin_headers, backup, pg):
    resp = _restore(client, admin_headers, backup.id, restore_service.current_db_name())
    assert _finished(client, admin_headers, resp)["status"] == "success"
    assert [r.status for r in _rows()] == ["success"]
    assert pg.upgraded == 1  # an older backup is brought up to this version


def test_failed_pg_restore_is_reported(client, admin_headers, backup, pg):
    pg.fail = "pg_restore"
    row = _finished(client, admin_headers, _restore(client, admin_headers, backup.id, "postgres"))
    assert row["status"] == "failed" and "boom" in row["error_message"]
    assert len(_rows()) == 1


def test_live_restore_pauses_other_requests(client, admin_headers, backup, pg):
    pg.hold = threading.Event()
    resp = _restore(client, admin_headers, backup.id, restore_service.current_db_name(), wait=False)
    assert resp.status_code == 202
    _until(lambda: pg.programs == ["pg_dump", "pg_restore"])

    status = client.get("/api/v1/backups/restore-status").get_json()
    assert status["running"] and status["active"]["live"] and status["active"]["phase"] == "restoring"
    busy = client.get("/api/v1/backups/restores", headers=admin_headers)
    assert busy.status_code == 503 and busy.get_json()["error"]["code"] == "RESTORE_IN_PROGRESS"
    assert client.get("/api/v1/health").status_code == 200

    pg.hold.set()
    restore_service.wait(10)
    status = client.get("/api/v1/backups/restore-status").get_json()
    assert not status["running"] and status["last"]["status"] == "success"
    assert client.get("/api/v1/backups/restores", headers=admin_headers).status_code == 200


def test_second_restore_while_one_runs_is_refused(client, admin_headers, backup, pg):
    pg.hold = threading.Event()
    backup_id = backup.id  # the request ends the shared test session, detaching `backup`
    assert _restore(client, admin_headers, backup_id, "postgres", wait=False).status_code == 202
    second = _restore(client, admin_headers, backup_id, "postgres", wait=False)
    assert second.status_code == 409 and "still running" in second.get_json()["error"]["message"]
    pg.hold.set()
    restore_service.wait(10)
    assert [r.status for r in _rows()] == ["success"]


def test_running_rows_not_under_way_are_closed_and_list_names_the_database(client, admin_headers, monkeypatch):
    cut_off = RestoreRecord(target_db="pos_db", status="running", started_at=datetime.now(timezone.utc))
    under_way = RestoreRecord(target_db="pos_db", status="running", started_at=datetime.now(timezone.utc))
    db.session.add_all([cut_off, under_way])
    db.session.commit()
    monkeypatch.setattr(restore_service, "_active", {"id": under_way.id, "live": False})

    body = client.get("/api/v1/backups/restores", headers=admin_headers).get_json()
    assert body["current_db"] == restore_service.current_db_name()
    status = {r["id"]: (r["status"], r["error_message"]) for r in body["items"]}
    assert status[cut_off.id][0] == "failed" and "Interrupted" in status[cut_off.id][1]
    assert status[under_way.id] == ("running", None)
