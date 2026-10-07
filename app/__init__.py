from flask import Flask
from app.config import Config
from app.extensions import db, login_manager


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Detras de un proxy con HTTPS (Nginx / Railway), respetar X-Forwarded-*.
    if app.config.get("BEHIND_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Inicializar extensiones
    db.init_app(app)
    login_manager.init_app(app)

    # Registrar rutas (blueprints)
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.products import products_bp
    from app.routes.customers import customers_bp
    from app.routes.sales import sales_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.reports import reports_bp
    from app.routes.purchases import purchases_bp
    from app.routes.supplier_orders import supplier_orders_bp
    from app.routes.settings import settings_bp
    from app.routes.sellers import sellers_bp
    from app.routes.employees import employees_bp
    from app.routes.expenses import expenses_bp
    from app.routes.hr import hr_bp
    from app.routes.alerts import alerts_bp
    from app.routes.backups import backups_bp
    from app.routes.users import users_bp
    from app.routes.guides import guides_bp
    from app.routes.dispatch import despachos_bp
    from app.routes.caja import caja_bp
    from app.routes.sri import sri_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(supplier_orders_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(sellers_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(backups_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(guides_bp)
    app.register_blueprint(despachos_bp)
    app.register_blueprint(caja_bp)
    app.register_blueprint(sri_bp)

    # Manejo simple de errores de permisos
    @app.errorhandler(403)
    def forbidden(e):
        return render_template_error(
            "No tienes permiso para ver esta página. Contacta al administrador.", 403
        )

    @app.context_processor
    def inject_globals():
        from datetime import datetime
        from flask import url_for
        logo_url = None
        try:
            from app.models import CompanySetting
            from app.utils import resolver_ruta_upload
            company = CompanySetting.actual()
            if company and resolver_ruta_upload(company.logo_path, app.config["LOGO_FOLDER"]):
                logo_url = url_for("settings.company_logo")
        except Exception:
            logo_url = None
        return {"current_year": datetime.now().year, "company_logo_url": logo_url}

    return app


def render_template_error(message, code):
    from flask import render_template
    return render_template("error.html", message=message), code
