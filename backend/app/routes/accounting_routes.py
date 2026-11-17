"""Accounting for Tally: ledger names, Day Book, GST summary, Tally import files."""
from flask import Blueprint, Response, jsonify, request

from app.extensions import db
from app.schemas.accounting_schemas import TallyLedgers
from app.schemas.report_schemas import ReportQuery
from app.services import accounting_service, audit_service, auth_service, tally_export_service
from app.utils.dates import business_date
from app.utils.permissions import require_permission
from app.utils.store_scope import scoped_store_id

accounting_bp = Blueprint("accounting", __name__)


def _query() -> ReportQuery:
    """?store_id=&date_from=&date_to= (inclusive IST dates; default today), limited to the actor's store."""
    q = ReportQuery.model_validate({k: v for k, v in request.args.items() if k in ReportQuery.model_fields})
    q.store_id = scoped_store_id(auth_service.current_user(), q.store_id)
    q.date_from = q.date_from or business_date()
    q.date_to = q.date_to or q.date_from
    return q


@accounting_bp.get("/accounting/ledgers")
@require_permission("settings.read")
def get_ledgers():
    return jsonify(accounting_service.get_ledgers().model_dump()), 200


@accounting_bp.put("/accounting/ledgers")
@require_permission("settings.manage")
def update_ledgers():
    data = TallyLedgers.model_validate(request.get_json(force=True))
    return jsonify(accounting_service.update_ledgers(data, auth_service.current_user()).model_dump()), 200


@accounting_bp.get("/accounting/daybook")
@require_permission("reports.read")
def day_book():
    q = _query()
    return jsonify(accounting_service.day_book(q.store_id, q.date_from, q.date_to).model_dump(mode="json")), 200


@accounting_bp.get("/accounting/gst-summary")
@require_permission("reports.read")
def gst_summary():
    q = _query()
    return jsonify(accounting_service.gst_summary(q.store_id, q.date_from, q.date_to).model_dump(mode="json")), 200


@accounting_bp.get("/accounting/tally-export")
@require_permission("reports.read")
def tally_export():
    """?what=vouchers (default) or ledgers: an XML file to import into Tally."""
    q = _query()
    what = request.args.get("what", "vouchers")
    vouchers, _warnings = accounting_service.build_vouchers(q.store_id, q.date_from, q.date_to)
    if what == "ledgers":
        xml = tally_export_service.ledgers_xml(vouchers, accounting_service.get_ledgers())
    else:
        what = "vouchers"
        xml = tally_export_service.vouchers_xml(vouchers)
    actor = auth_service.current_user()
    audit_service.log(actor, "accounting.tally_export", "accounting", None, None, {
        "what": what, "store_id": q.store_id, "date_from": str(q.date_from), "date_to": str(q.date_to),
        "vouchers": len(vouchers),
    })
    db.session.commit()
    store = f"-store{q.store_id}" if q.store_id else ""
    name = f"tally-{what}{store}-{q.date_from:%Y%m%d}-{q.date_to:%Y%m%d}.xml"
    return Response(xml, mimetype="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
