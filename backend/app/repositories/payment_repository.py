"""Payment queries."""
from app.extensions import db
from app.models.payment import Payment
from app.repositories.base_repository import BaseRepository


class PaymentRepository(BaseRepository):
    model = Payment

    def list_for_sale(self, sale_id: int) -> list[Payment]:
        q = db.select(Payment).where(Payment.sale_id == sale_id).order_by(Payment.id)
        return list(db.session.scalars(q).all())
