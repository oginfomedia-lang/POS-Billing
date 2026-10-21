"""Batch-wise stock: batches from stock-in / goods receipts, sales take the earliest expiry first (FEFO), returns go
back to their batch, stock-take and write-offs, expiry list, and batches always adding up to the stock."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.inventory import Inventory, SaleItemBatch, StockBatch
from tests.factories import make_counter, make_product, make_shift, make_user

pytestmark = pytest.mark.integration

TODAY = date.today()


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store), opening_float="500.00")


@pytest.fixture
def manager(store):
    return make_user(role="manager", username="mgr", pin="4321", store=store)


def _stock_in(client, headers, store, product, qty, expiry=None, batch=None):
    body = {"store_id": store.id, "product_id": product.id, "qty": str(qty),
            "expiry_date": expiry.isoformat() if expiry else None, "batch_number": batch}
    resp = client.post("/api/v1/inventory/stock-in", json=body, headers=headers)
    assert resp.status_code == 200, resp.get_json()


def _sell(client, headers, product, qty):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "10000"}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _batches(client, headers, store, product):
    resp = client.get("/api/v1/inventory/batches", query_string={"store_id": store.id, "product_id": product.id},
                      headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return {b["batch_number"]: Decimal(b["qty_remaining"]) for b in resp.get_json()}


def _assert_batches_match_stock(store, product):
    db.session.expire_all()
    on_hand = db.session.scalar(
        db.select(Inventory.qty_on_hand).where(Inventory.store_id == store.id, Inventory.product_id == product.id))
    in_batches = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(StockBatch.qty_remaining), 0))
        .where(StockBatch.store_id == store.id, StockBatch.product_id == product.id))
    assert Decimal(in_batches) == Decimal(on_hand)


def test_sale_takes_the_batch_that_expires_first(client, admin_headers, cashier_headers, shift, store):
    milk = make_product(store, name="Milk", stock=0)
    _stock_in(client, admin_headers, store, milk, 5, TODAY + timedelta(days=20), "LATE")
    _stock_in(client, admin_headers, store, milk, 3, TODAY + timedelta(days=5), "SOON")
    _stock_in(client, admin_headers, store, milk, 4, None, "NOEXP")

    bill = _sell(client, cashier_headers, milk, 4)  # 3 from SOON, then 1 from LATE
    assert _batches(client, admin_headers, store, milk) == {"LATE": Decimal("4"), "NOEXP": Decimal("4")}

    allocations = db.session.scalars(
        db.select(SaleItemBatch).where(SaleItemBatch.sale_item_id == bill["items"][0]["id"])).all()
    assert sorted((a.batch.batch_number, a.qty) for a in allocations) == [("LATE", 1), ("SOON", 3)]
    _assert_batches_match_stock(store, milk)


def test_expired_batches_are_not_sold_while_good_stock_is_left(client, admin_headers, cashier_headers, shift, store):
    curd = make_product(store, name="Curd", stock=0)
    _stock_in(client, admin_headers, store, curd, 2, TODAY - timedelta(days=1), "EXPIRED")
    _stock_in(client, admin_headers, store, curd, 3, TODAY + timedelta(days=3), "FRESH")
    _sell(client, cashier_headers, curd, 2)
    assert _batches(client, admin_headers, store, curd) == {"FRESH": Decimal("1"), "EXPIRED": Decimal("2")}


def test_return_goes_back_to_the_batch_it_was_sold_from(client, admin_headers, cashier_headers, shift, store, manager):
    oil = make_product(store, name="Oil", stock=0)
    _stock_in(client, admin_headers, store, oil, 2, TODAY + timedelta(days=30), "A")
    _stock_in(client, admin_headers, store, oil, 5, TODAY + timedelta(days=90), "B")
    bill = _sell(client, cashier_headers, oil, 3)  # A: 2, B: 1
    assert _batches(client, admin_headers, store, oil) == {"B": Decimal("4")}

    resp = client.post("/api/v1/returns", json={
        "bill_number": bill["bill_number"], "lines": [{"sale_item_id": bill["items"][0]["id"], "qty": 1}],
        "reason": "Leaking", "approver_username": "mgr", "approver_pin": "4321",
    }, headers=cashier_headers)
    assert resp.status_code == 201, resp.get_json()
    batches = _batches(client, admin_headers, store, oil)
    assert sum(batches.values()) == Decimal("5")
    assert set(batches) <= {"A", "B"}  # back into a batch the bill came from, not a new one
    _assert_batches_match_stock(store, oil)


def test_stock_take_down_takes_fefo_and_up_adds_a_batch(client, admin_headers, store):
    rice = make_product(store, name="Rice", stock=0)
    _stock_in(client, admin_headers, store, rice, 10, TODAY + timedelta(days=60), "OLD")
    _stock_in(client, admin_headers, store, rice, 10, TODAY + timedelta(days=200), "NEW")

    adjust = lambda qty: client.post("/api/v1/inventory/adjust", json={
        "store_id": store.id, "product_id": rice.id, "new_qty": str(qty), "notes": "count"}, headers=admin_headers)
    assert adjust(16).status_code == 200
    assert _batches(client, admin_headers, store, rice) == {"OLD": Decimal("6"), "NEW": Decimal("10")}
    assert adjust(18).status_code == 200
    assert _batches(client, admin_headers, store, rice) == {"OLD": Decimal("6"), "NEW": Decimal("10"), None: Decimal("2")}
    _assert_batches_match_stock(store, rice)


def test_goods_receipt_creates_a_batch_with_its_number_and_cost(app, store, admin_user):
    from app.models.enums import PurchaseStatus
    from app.models.purchase import PurchaseOrder, PurchaseOrderItem
    from app.models.supplier import Supplier
    from app.schemas.purchase_schemas import GoodsReceiptCreate
    from app.services import purchase_service

    soap = make_product(store, name="Soap", stock=0)
    supplier = Supplier(supplier_code="SUP-B1", company_name="Batch Traders")
    db.session.add(supplier)
    db.session.flush()
    po = PurchaseOrder(po_number="PO-B1", supplier_id=supplier.id, store_id=store.id, status=PurchaseStatus.ORDERED,
                       purchase_date=TODAY, created_by_id=admin_user.id)
    po.items.append(PurchaseOrderItem(product_id=soap.id, product_name="Soap", ordered_qty=12, unit_price=Decimal("20"),
                                      discount_percent=Decimal("10"), tax_rate=Decimal("18"),
                                      line_total=Decimal("216")))
    db.session.add(po)
    db.session.commit()

    data = GoodsReceiptCreate.model_validate({"items": [{
        "purchase_order_item_id": po.items[0].id, "qty_received": 12, "batch_number": "SP-77",
        "mfg_date": (TODAY - timedelta(days=10)).isoformat(), "expiry_date": (TODAY + timedelta(days=365)).isoformat(),
    }]})
    purchase_service.receive_goods(po.id, data, admin_user)
    batch = db.session.scalar(db.select(StockBatch).where(StockBatch.product_id == soap.id))
    assert (batch.batch_number, batch.qty_remaining, batch.unit_cost, batch.source) == (
        "SP-77", Decimal("12.000"), Decimal("18.0000"), "grn")
    _assert_batches_match_stock(store, soap)


def test_write_off_an_expired_batch(client, admin_headers, store):
    bread = make_product(store, name="Bread", stock=0)
    _stock_in(client, admin_headers, store, bread, 4, TODAY - timedelta(days=2), "STALE")
    _stock_in(client, admin_headers, store, bread, 6, TODAY + timedelta(days=2), "OK")
    stale = db.session.scalar(db.select(StockBatch).where(StockBatch.batch_number == "STALE"))

    too_much = client.post(f"/api/v1/inventory/batches/{stale.id}/write-off", json={"qty": "5", "reason": "Expired"},
                           headers=admin_headers)
    assert too_much.status_code == 400
    resp = client.post(f"/api/v1/inventory/batches/{stale.id}/write-off", json={"reason": "Expired"},
                       headers=admin_headers)
    assert resp.status_code == 200, resp.get_json()
    assert _batches(client, admin_headers, store, bread) == {"OK": Decimal("6")}
    _assert_batches_match_stock(store, bread)


def test_cashier_cannot_write_off(client, admin_headers, cashier_headers, store):
    jam = make_product(store, name="Jam", stock=0)
    _stock_in(client, admin_headers, store, jam, 1, TODAY, "J1")
    batch = db.session.scalar(db.select(StockBatch).where(StockBatch.batch_number == "J1"))
    assert client.post(f"/api/v1/inventory/batches/{batch.id}/write-off", json={"reason": "x"},
                       headers=cashier_headers).status_code == 403


def test_expiry_list_shows_each_batch_including_expired(client, admin_headers, store):
    paneer = make_product(store, name="Paneer", stock=0)
    _stock_in(client, admin_headers, store, paneer, 2, TODAY - timedelta(days=1), "P-OLD")
    _stock_in(client, admin_headers, store, paneer, 3, TODAY + timedelta(days=10), "P-NEW")
    _stock_in(client, admin_headers, store, paneer, 9, TODAY + timedelta(days=100), "P-LATER")
    rows = client.get("/api/v1/inventory/expiring", query_string={"store_id": store.id},
                      headers=admin_headers).get_json()
    assert [(r["batch_number"], r["days_to_expiry"], Decimal(r["batch_qty"])) for r in rows] == [
        ("P-OLD", -1, Decimal("2")), ("P-NEW", 10, Decimal("3"))]
    assert all(Decimal(r["qty_on_hand"]) == Decimal("14") for r in rows)

    dashboard = client.get("/api/v1/reports/dashboard", query_string={"store_id": store.id}, headers=admin_headers)
    assert dashboard.get_json()["near_expiry"] == 1  # one product, two batches
