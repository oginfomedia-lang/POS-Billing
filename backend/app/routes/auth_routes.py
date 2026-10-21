"""Login, refresh, and current-user endpoints."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.schemas.auth_schemas import LoginRequest, RefreshResponse, TokenResponse, UserOut
from app.services import auth_service

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/auth/login")
def login():
    data = LoginRequest.model_validate(request.get_json(force=True))
    access_token, refresh_token, user = auth_service.login(data.username, data.pin)
    resp = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )
    return jsonify(resp.model_dump(mode="json")), 200


@auth_bp.post("/auth/refresh")
@jwt_required(refresh=True)
def refresh():
    """Issue a fresh access token using a valid refresh token."""
    user = auth_service.current_user()
    new_access = auth_service.new_access_token(user)
    resp = RefreshResponse(access_token=new_access)
    return jsonify(resp.model_dump(mode="json")), 200


@auth_bp.get("/auth/me")
@jwt_required()
def me():
    user = auth_service.current_user()
    return jsonify(UserOut.model_validate(user).model_dump(mode="json")), 200
