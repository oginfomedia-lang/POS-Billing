"""The background scheduler must run once: not in the dev server's reloader watcher process as well."""
from types import SimpleNamespace

from app.scheduler.setup import _is_reloader_watcher


def test_dev_watcher_process_skips_the_scheduler(monkeypatch):
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    assert _is_reloader_watcher(SimpleNamespace(debug=True))


def test_dev_worker_process_runs_it(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    assert not _is_reloader_watcher(SimpleNamespace(debug=True))


def test_production_always_runs_it(monkeypatch):
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    assert not _is_reloader_watcher(SimpleNamespace(debug=False))
