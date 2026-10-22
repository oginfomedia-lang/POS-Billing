"""Password hashing and verification."""
from werkzeug.security import check_password_hash, generate_password_hash


def hash_pin(pin: str) -> str:
    return generate_password_hash(pin)


def check_user_pin(user, pin: str) -> bool:
    """verify_pin() with a limit on guessing: after PIN_MAX_FAILURES wrong PINs in a row the user is locked for
    PIN_LOCK_MINUTES (login and manager approvals alike). The count is saved at once, even when the request
    then fails, and is shared by every counter. Raises TooManyAttemptsError while locked."""
    from datetime import datetime, timedelta, timezone

    from flask import current_app

    from app.errors.exceptions import TooManyAttemptsError
    from app.extensions import db

    now = datetime.now(timezone.utc)
    if user.pin_locked_until is not None and user.pin_locked_until > now:
        minutes = max(1, -(-int((user.pin_locked_until - now).total_seconds()) // 60))
        raise TooManyAttemptsError(
            f"Too many wrong PINs for '{user.username}'. Try again in {minutes} minute{'s' if minutes > 1 else ''}, "
            "or ask an admin to reset the PIN."
        )
    if verify_pin(pin, user.pin_hash):
        if user.pin_failures or user.pin_locked_until:
            user.pin_failures, user.pin_locked_until = 0, None
            db.session.commit()
        return True
    user.pin_failures = (user.pin_failures or 0) + 1
    if user.pin_failures >= current_app.config["PIN_MAX_FAILURES"]:
        user.pin_failures = 0
        user.pin_locked_until = now + timedelta(minutes=current_app.config["PIN_LOCK_MINUTES"])
    db.session.commit()
    return False


def verify_pin(pin: str, hashed: str) -> bool:
    return check_password_hash(hashed, pin)
