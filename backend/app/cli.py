"""Flask CLI commands: flask create-admin, flask send-daily-collection, flask send-ebills.

First-time setup on a fresh server (run from backend/, after `flask db upgrade`):

    flask create-admin --username owner --full-name "Store Owner"

It asks for the PIN twice (hidden). The admin then signs in and creates stores,
counters and every other user from the admin screens.

The nightly WhatsApp collection summary is sent by Windows Task Scheduler running, every 15 minutes:

    flask send-daily-collection

E-bills go out on WhatsApp as soon as a bill is paid; failed ones are retried by Task Scheduler running,
every 5 minutes:

    flask send-ebills
"""
from datetime import datetime

import click
import pydantic
from flask import Flask

from app.errors.exceptions import AppError
from app.extensions import db
from app.models.enums import UserRole
from app.repositories.store_repository import StoreRepository
from app.schemas.user_schemas import UserCreate
from app.services import daily_report_service, ebill_service, settings_service, user_service


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


@click.command("send-daily-collection")
@click.option("--date", "day", type=click.DateTime(["%Y-%m-%d"]), default=None,
              help="Send this day's summary now (YYYY-MM-DD) instead of waiting for the configured time.")
@click.option("--force", is_flag=True, help="With --date: send again even if it was already sent.")
def send_daily_collection(day: datetime | None, force: bool) -> None:
    """Send the daily collection summary on WhatsApp if it's due (run every 15 min by Task Scheduler)."""
    if day is None:
        results = daily_report_service.run_due()
    else:
        mobiles = settings_service.get_settings().report_mobiles
        if not mobiles:
            raise click.ClickException("No mobile numbers set for the daily report (Admin > Settings).")
        results = daily_report_service.send_for_date(day.date(), mobiles, force=force)
    if not results:
        click.echo("Nothing to send (switched off, not time yet, or already sent).")
    for r in results:
        click.echo(f"{r.store_name} -> {r.recipient}: {r.status}{f' ({r.error})' if r.error else ''}")


@click.command("send-ebills")
def send_ebills() -> None:
    """Retry WhatsApp e-bills that failed or weren't sent (run every 5 min by Task Scheduler)."""
    results = ebill_service.retry_due()
    if not results:
        click.echo("No e-bills waiting.")
    for r in results:
        click.echo(f"{r.store_name} -> {r.recipient}: {r.status}{f' ({r.error})' if r.error else ''}")


@click.command("check-products")
def check_products() -> None:
    """List products saved with a price, MRP or GST rate the product form no longer accepts (read-only).

    Installed shop:  literetailer-backend.exe flask check-products
    Fix each one in Admin → Products; nothing is changed here.
    """
    from app.models.product import Product

    bad = db.session.scalars(
        db.select(Product).where(
            db.or_(Product.price < 0, Product.mrp < 0, Product.tax_rate < 0, Product.tax_rate > 100)
        ).order_by(Product.id)
    ).all()
    if not bad:
        click.echo("All products have a valid price, MRP and GST rate.")
        return
    click.echo(f"{len(bad)} product(s) to correct in Admin → Products:")
    for p in bad:
        click.echo(f"  #{p.id} {p.sku}  {p.name}: price {p.price}, MRP {p.mrp}, GST {p.tax_rate}%"
                   f"{'' if p.is_active else '  (inactive)'}")
    raise SystemExit(1)


def register_cli(app: Flask) -> None:
    app.cli.add_command(check_products)
    app.cli.add_command(create_admin)
    app.cli.add_command(send_daily_collection)
    app.cli.add_command(send_ebills)
