"""App update files for electron-updater on every PC (no login: the updater can't send one), and their status."""
from flask import Blueprint, abort, jsonify, send_from_directory

from app.services import update_mirror_service
from app.utils.permissions import require_permission

update_bp = Blueprint("updates", __name__)


@update_bp.get("/updates/<string:filename>")
def update_file(filename: str):
    if filename != update_mirror_service.LATEST and not update_mirror_service.SAFE_NAME.match(filename):
        abort(404)
    folder = update_mirror_service.updates_dir()
    if not (folder / filename).is_file():
        abort(404)
    # latest.yml must never be cached: it is how the apps learn about a new version.
    return send_from_directory(folder, filename, max_age=0)


@update_bp.get("/updates-status")
@require_permission("settings.read")
def update_status():
    return jsonify(update_mirror_service.status()), 200
