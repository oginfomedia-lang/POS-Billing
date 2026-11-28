"""AppError, NotFoundError, ValidationError, ConflictError, InsufficientStockError, PermissionDeniedError.

Services raise these. errors/handlers.py turns them into JSON responses:
    {"error": {"code": "...", "message": "...", "details": ...}}
"""
from typing import Any


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, details: Any = None):
        super().__init__(message)
        self.message = message
        self.details = details


class BadRequestError(AppError):
    status_code = 400
    code = "BAD_REQUEST"



class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "PERMISSION_DENIED"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class TooManyAttemptsError(AppError):
    """Too many wrong PINs for one user: login and approvals with that user wait a few minutes."""

    status_code = 429
    code = "TOO_MANY_ATTEMPTS"


class PlanLimitError(AppError):
    """The shop's plan allows fewer counters / stores / users than this would need."""

    status_code = 403
    code = "PLAN_LIMIT_REACHED"


class InsufficientStockError(AppError):
    """details = [{"product_id": ..., "product_name": ..., "requested": ..., "available": ...}]"""

    status_code = 400
    code = "INSUFFICIENT_STOCK"
