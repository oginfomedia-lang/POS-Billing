"""Login, token creation, current-user helper."""
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity

from app.errors.exceptions import UnauthorizedError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.utils.security import check_user_pin


def login(username: str, pin: str) -> tuple[str, str, User]:
    """Return (access_token, refresh_token, user)."""
    repo = UserRepository()
    user = repo.get_by_username(username)

    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid username or PIN.")
    if not check_user_pin(user, pin):
        raise UnauthorizedError("Invalid username or PIN.")

    access_token, refresh_token = new_tokens(user)
    return access_token, refresh_token, user


def new_tokens(user: User) -> tuple[str, str]:
    """(access_token, refresh_token) for a user who just proved their PIN."""
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims={"sv": user.session_version})
    return new_access_token(user), refresh_token


def new_access_token(user: User) -> str:
    claims = {"role": user.role.value, "username": user.username, "sv": user.session_version}
    if user.must_change_pin:
        claims["pc"] = True  # PIN change required: only the change-PIN screen works (see app.__init__)
    return create_access_token(identity=str(user.id), additional_claims=claims)


def session_ended(jwt_payload: dict) -> bool:
    """True when the token's user is gone or deactivated, or their PIN / role / store changed after it was
    issued. Tokens from before this check have no "sv": they count as 0, the value every user starts with."""
    try:
        user = UserRepository().get_by_id(int(jwt_payload["sub"]))
    except (KeyError, TypeError, ValueError):
        return True
    return user is None or not user.is_active or jwt_payload.get("sv", 0) != user.session_version


def current_user() -> User:
    user_id = int(get_jwt_identity())
    user = UserRepository().get_by_id(user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("User account not found or deactivated.")
    return user
