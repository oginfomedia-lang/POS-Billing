"""System setting and backup run queries."""
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models.system import SystemSetting


class SettingsRepository:
    def all(self) -> dict[str, str]:
        return {s.key: s.value for s in db.session.scalars(db.select(SystemSetting)).all()}

    def delete(self, key: str) -> bool:
        """Removes a setting. Returns whether it existed."""
        return db.session.execute(db.delete(SystemSetting).where(SystemSetting.key == key)).rowcount > 0

    def upsert(self, key: str, value: str, user_id: int | None) -> None:
        stmt = insert(SystemSetting).values(key=key, value=value, updated_by=user_id)
        db.session.execute(
            stmt.on_conflict_do_update(
                index_elements=[SystemSetting.key],
                set_={"value": stmt.excluded.value, "updated_by": stmt.excluded.updated_by, "updated_at": db.func.now()},
            )
        )
