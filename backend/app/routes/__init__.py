"""Registers all blueprints under /api/v1. Routes contain no business logic."""
from flask import Flask

from app.routes.audit_routes import audit_bp
from app.routes.backup_routes import backup_bp
from app.routes.auth_routes import auth_bp
from app.routes.billing_routes import billing_bp
from app.routes.customer_routes import customer_bp
from app.routes.discount_routes import discount_bp
from app.routes.health_routes import health_bp
from app.routes.inventory_routes import inventory_bp
from app.routes.product_routes import product_bp
from app.routes.receipt_routes import receipt_bp
from app.routes.report_routes import report_bp
from app.routes.return_routes import return_bp
from app.routes.settings_routes import settings_bp
from app.routes.shift_routes import shift_bp
from app.routes.store_routes import store_bp
from app.routes.supplier_routes import supplier_bp
from app.routes.purchase_routes import purchase_bp
from app.routes.user_routes import user_bp


def register_blueprints(app: Flask) -> None:
    prefix = app.config["API_PREFIX"]
    app.register_blueprint(health_bp, url_prefix=prefix)
    app.register_blueprint(auth_bp, url_prefix=prefix)
    app.register_blueprint(user_bp, url_prefix=prefix)
    app.register_blueprint(store_bp, url_prefix=prefix)
    app.register_blueprint(audit_bp, url_prefix=prefix)
    app.register_blueprint(shift_bp, url_prefix=prefix)
    app.register_blueprint(product_bp, url_prefix=prefix)
    app.register_blueprint(inventory_bp, url_prefix=prefix)
    app.register_blueprint(billing_bp, url_prefix=prefix)
    app.register_blueprint(receipt_bp, url_prefix=prefix)
    app.register_blueprint(return_bp, url_prefix=prefix)
    app.register_blueprint(discount_bp, url_prefix=prefix)
    app.register_blueprint(report_bp, url_prefix=prefix)
    app.register_blueprint(settings_bp, url_prefix=prefix)
    app.register_blueprint(backup_bp, url_prefix=prefix)
    app.register_blueprint(supplier_bp, url_prefix=prefix)
    app.register_blueprint(purchase_bp, url_prefix=prefix)
    app.register_blueprint(customer_bp, url_prefix=prefix)
