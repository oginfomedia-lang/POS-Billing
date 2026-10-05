"""Login, token creation, current-user helper."""
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity

from app.errors.exceptions import UnauthorizedError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.utils.security import verify_pin


def login(username: str, pin: str) -> tuple[str, str, User]:
    """Return (access_token, refresh_token, user)."""
    repo = UserRepository()
    user = repo.get_by_username(username)

    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid username or PIN.")
    if not verify_pin(pin, user.pin_hash):
        raise UnauthorizedError("Invalid username or PIN.")

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role.value, "username": user.username},
    )
    refresh_token = create_refresh_token(identity=str(user.id))
    return access_token, refresh_token, user


def current_user() -> User:
    user_id = int(get_jwt_identity())
    user = UserRepository().get_by_id(user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("User account not found or deactivated.")
    return user
