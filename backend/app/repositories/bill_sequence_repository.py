"""next_number(): INSERT ... ON CONFLICT DO UPDATE ... RETURNING last_number."""
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models.sale import BillSequence


class BillSequenceRepository:
    def next_number(self, store_id: int) -> int:
        """Atomically increments and returns the store's bill counter (row-locked until commit)."""
        stmt = (
            insert(BillSequence)
            .values(store_id=store_id, last_number=1)
            .on_conflict_do_update(
                index_elements=[BillSequence.store_id],
                set_={"last_number": BillSequence.last_number + 1},
            )
            .returning(BillSequence.last_number)
        )
        return db.session.execute(stmt).scalar_one()
