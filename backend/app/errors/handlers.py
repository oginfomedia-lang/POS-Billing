"""Converts exceptions into consistent JSON error responses."""
from typing import Any

import pydantic
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from app.errors.exceptions import AppError
from app.extensions import db


def error_response(status_code: int, code: str, message: str, details: Any = None):
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status_code


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        db.session.rollback()
        return error_response(err.status_code, err.code, err.message, err.details)

    @app.errorhandler(pydantic.ValidationError)
    def handle_validation_error(err: pydantic.ValidationError):
        details = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
            for e in err.errors()
        ]
        return error_response(422, "VALIDATION_ERROR", "Invalid request data.", details)

    @app.errorhandler(HTTPException)
    def handle_http_error(err: HTTPException):
        code = (err.name or "HTTP_ERROR").upper().replace(" ", "_")
        return error_response(err.code or 500, code, err.description or err.name)

    @app.errorhandler(Exception)
    def handle_unexpected_error(err: Exception):
        db.session.rollback()
        app.logger.exception("Unhandled error")
        return error_response(500, "INTERNAL_ERROR", "Something went wrong on the server.")
