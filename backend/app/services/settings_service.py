"""Read/update system settings, backup status.

Backup status isn't implemented yet: the backup scripts in scripts/backup are still stubs.
"""
from __future__ import annotations

from app.models.user import User
from app.repositories.settings_repository import SettingsRepository
from app.schemas.settings_schemas import SettingsData
from app.services import audit_service
from app.utils.transactions import transaction


def get_settings() -> SettingsData:
    """Saved values over the defaults declared on SettingsData."""
    saved = SettingsRepository().all()
    known = {k: v for k, v in saved.items() if k in SettingsData.model_fields}
    return SettingsData.model_validate(known)


def update_settings(data: SettingsData, actor: User) -> SettingsData:
    old = get_settings().model_dump(mode="json")
    new = data.model_dump(mode="json")
    repo = SettingsRepository()
    with transaction():
        for key, value in new.items():
            repo.upsert(key, str(value), actor.id)
        changed = {k for k in new if new[k] != old[k]}
        if changed:
            audit_service.log(
                actor, "settings.update", "settings", None,
                {k: old[k] for k in changed}, {k: new[k] for k in changed},
            )
    return get_settings()
