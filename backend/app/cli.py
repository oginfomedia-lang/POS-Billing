"""Flask CLI commands: flask create-admin.

First-time setup on a fresh server (run from backend/, after `flask db upgrade`):

    flask create-admin --username owner --full-name "Store Owner"

It asks for the PIN twice (hidden). The admin then signs in and creates stores,
counters and every other user from the admin screens.
"""
import click
import pydantic
from flask import Flask

from app.errors.exceptions import AppError
from app.models.enums import UserRole
from app.repositories.store_repository import StoreRepository
from app.schemas.user_schemas import UserCreate
from app.services import user_service


@click.command("create-admin")
@click.option("--username", prompt=True, help="Lowercase letters, digits and _ (3-50 chars).")
@click.option("--full-name", prompt=True, help="Name shown in the app and on audit logs.")
@click.option("--store-id", type=int, default=None, help="Optional store to assign the admin to.")
@click.option(
    "--pin",
    prompt="PIN (4-8 digits)",
    hide_input=True,
    confirmation_prompt=True,
    help="Omit to be prompted (recommended, so the PIN isn't saved in shell history).",
)
def create_admin(username: str, full_name: str, store_id: int | None, pin: str) -> None:
    """Create an admin user (use once on a new installation, or to recover access)."""
    try:
        data = UserCreate(username=username, full_name=full_name, pin=pin, role=UserRole.ADMIN, store_id=store_id)
    except pydantic.ValidationError as err:
        msgs = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in err.errors())
        raise click.ClickException(msgs) from None

    if store_id is not None and StoreRepository().get_by_id(store_id) is None:
        raise click.ClickException(f"Store {store_id} does not exist.")

    try:
        user = user_service.create_user(data, actor=None)  # audited with no actor = created from the CLI
    except AppError as err:
        raise click.ClickException(err.message) from None
    click.echo(f"Admin '{user.username}' created (id {user.id}). Sign in to the app with this username and PIN.")


def register_cli(app: Flask) -> None:
    app.cli.add_command(create_admin)
