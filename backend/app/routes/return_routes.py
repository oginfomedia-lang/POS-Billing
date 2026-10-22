"""Returns: look up a bill, create a return (cash refund, manager PIN), fetch a credit note for printing."""
from flask import Blueprint, jsonify, request

from app.schemas.return_schemas import CreateReturnRequest
from app.services import auth_service, return_service
from app.utils.permissions import require_permission

return_bp = Blueprint("returns", __name__)


@return_bp.get("/returns/bill/<path:bill_number>")
@require_permission("sales.read")
def returnable_bill(bill_number: str):
    bill = return_service.returnable_bill(bill_number, auth_service.current_user())
    return jsonify(bill.model_dump(mode="json")), 200


@return_bp.get("/returns/bills")
@require_permission("sales.read")
def bills_for_mobile():
    bills = return_service.bills_for_mobile(request.args.get("mobile", ""), auth_service.current_user())
    return jsonify([b.model_dump(mode="json") for b in bills]), 200


@return_bp.post("/returns")
@require_permission("sales.create")
def create_return():
    data = CreateReturnRequest.model_validate(request.get_json(force=True))
    ret = return_service.create_return(data, auth_service.current_user())
    return jsonify(return_service.to_out(ret).model_dump(mode="json")), 201


@return_bp.get("/returns/<int:return_id>")
@require_permission("sales.read")
def get_return(return_id: int):
    ret = return_service.get_return(return_id, auth_service.current_user())
    return jsonify(return_service.to_out(ret).model_dump(mode="json")), 200
