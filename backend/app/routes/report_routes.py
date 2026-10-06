"""Report endpoints."""
from flask import Blueprint, jsonify, request

from app.schemas.report_schemas import ReportQuery
from app.services import report_service
from app.utils.permissions import require_permission

report_bp = Blueprint("reports", __name__)


@report_bp.get("/reports/dashboard")
@require_permission("reports.read")
def dashboard():
    store_id = request.args.get("store_id", type=int)
    return jsonify(report_service.dashboard(store_id).model_dump(mode="json")), 200


@report_bp.get("/reports/sales")
@require_permission("reports.read")
def sales_report():
    q = ReportQuery.model_validate(request.args.to_dict())
    return jsonify(report_service.sales_report(q).model_dump(mode="json")), 200


@report_bp.get("/reports/shifts")
@require_permission("reports.read")
def shift_report():
    q = ReportQuery.model_validate(request.args.to_dict())
    return jsonify([r.model_dump(mode="json") for r in report_service.shift_report(q)]), 200
