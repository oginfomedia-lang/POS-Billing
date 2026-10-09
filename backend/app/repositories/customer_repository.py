"""Customer and reward-points queries. add_txn() is the ONLY place that changes a points balance."""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models.customer import Customer, RewardTransaction
from app.models.enums import RewardTxnType
from app.models.returns import SaleReturn
from app.models.user import User


class CustomerRepository:
    def get_by_mobile(self, mobile: str) -> Customer | None:
        """Plain read (payment screen balance). Doesn't create anything."""
        return db.session.scalar(db.select(Customer).where(Customer.mobile == mobile))

    def get_by_id(self, customer_id: int) -> Customer | None:
        return db.session.get(Customer, customer_id)

    def get_or_create_for_update(self, mobile: str) -> Customer:
        """The customer for this mobile, created on the first paid bill, locked until commit.

        INSERT ... ON CONFLICT DO NOTHING: two counters billing a new customer at the same moment
        can't create two rows (mobile is UNIQUE). FOR UPDATE: the second counter waits here until the
        first bill commits, so the same points can never be spent twice.
        """
        stmt = insert(Customer).values(mobile=mobile, created_at=db.func.now(), updated_at=db.func.now())
        db.session.execute(stmt.on_conflict_do_nothing(index_elements=[Customer.mobile]))
        q = (
            db.select(Customer)
            .where(Customer.mobile == mobile)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return db.session.scalars(q).one()

    def lock(self, customer_id: int) -> Customer | None:
        q = (
            db.select(Customer)
            .where(Customer.id == customer_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return db.session.scalars(q).first()

    def add_txn(
        self,
        customer: Customer,
        txn_type: RewardTxnType,
        points: int,
        *,
        sale_id: int | None = None,
        return_id: int | None = None,
        note: str | None = None,
        user: User | None = None,
    ) -> RewardTransaction:
        """Changes the balance and writes the passbook line in one step, so the two can't disagree."""
        customer.points_balance += points
        if txn_type is RewardTxnType.REDEEM:
            customer.lifetime_redeemed += -points
        else:  # EARN (+), REVERSE (−, earned points taken back), ADJUST (±)
            customer.lifetime_earned += points
        txn = RewardTransaction(
            customer=customer,
            sale_id=sale_id,
            return_id=return_id,
            txn_type=txn_type,
            points=points,
            balance_after=customer.points_balance,
            note=note,
            created_by_id=user.id if user else None,
        )
        db.session.add(txn)
        return txn

    def reversed_for_sale(self, sale_id: int) -> int:
        """Earned points already taken back by earlier returns of this bill (positive number)."""
        q = db.select(db.func.coalesce(db.func.sum(RewardTransaction.points), 0)).where(
            RewardTransaction.sale_id == sale_id, RewardTransaction.txn_type == RewardTxnType.REVERSE
        )
        return -int(db.session.scalar(q) or 0)

    def refunded_for_sale(self, sale_id: int):
        """Total refunded on this bill so far, including a return added in the current transaction."""
        db.session.flush()
        q = db.select(db.func.coalesce(db.func.sum(SaleReturn.refund_amount), 0)).where(SaleReturn.sale_id == sale_id)
        return db.session.scalar(q)

    def search(self, text: str | None, page: int = 1, per_page: int = 25) -> tuple[list[Customer], int]:
        q = db.select(Customer)
        if text and text.strip():
            needle = text.strip()
            q = q.where(db.or_(Customer.mobile.contains(needle), Customer.name.ilike(f"%{needle}%")))
        total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery())) or 0
        q = q.order_by(Customer.last_visit_at.desc().nulls_last(), Customer.id.desc())
        items = db.session.scalars(q.offset((page - 1) * per_page).limit(per_page)).all()
        return list(items), total

    def ledger(self, customer_id: int, page: int = 1, per_page: int = 50) -> tuple[list[RewardTransaction], int]:
        q = db.select(RewardTransaction).where(RewardTransaction.customer_id == customer_id)
        total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery())) or 0
        q = q.order_by(RewardTransaction.id.desc()).offset((page - 1) * per_page).limit(per_page)
        return list(db.session.scalars(q).all()), total
