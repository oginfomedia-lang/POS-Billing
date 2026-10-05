"""Password hashing and verification."""
from werkzeug.security import check_password_hash, generate_password_hash


def hash_pin(pin: str) -> str:
    return generate_password_hash(pin)


def verify_pin(pin: str, hashed: str) -> bool:
    return check_password_hash(hashed, pin)
