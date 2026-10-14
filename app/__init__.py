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
    from app.routes.push import push_bp
    from app.routes.alerts import alerts_bp
    from app.routes.backups import backups_bp
    from app.routes.users import users_bp
    from app.routes.guides import guides_bp
    from app.routes.dispatch import despachos_bp
    from app.routes.caja import caja_bp
    from app.routes.sri import sri_bp
    from app.routes.transfers import transfers_bp
    from app.routes.importar import importar_bp

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
    app.register_blueprint(push_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(backups_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(guides_bp)
    app.register_blueprint(despachos_bp)
    app.register_blueprint(caja_bp)
    app.register_blueprint(sri_bp)
    app.register_blueprint(transfers_bp)
    app.register_blueprint(importar_bp)

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
        system_name = "Sistema de Facturación"
        try:
            from app.models import CompanySetting
            from app.utils import resolver_ruta_upload
            company = CompanySetting.actual()
            if company and resolver_ruta_upload(company.logo_path, app.config["LOGO_FOLDER"]):
                logo_url = url_for("settings.company_logo")
            if company and company.system_name:
                system_name = company.system_name
        except Exception:
            logo_url = None
        try:
            from app.stock import etiqueta_ubicacion, listar_ubicaciones, stock_en
            ubicaciones = listar_ubicaciones()
            ubicacion_label = etiqueta_ubicacion
        except Exception:
            ubicaciones = [("local", "Bodega Local"), ("matriz", "Bodega Matriz")]
            ubicacion_label = lambda u: {"local": "Bodega Local", "matriz": "Bodega Matriz"}.get(u, u or "—")
            stock_en = lambda p, u: (p.current_stock or 0)
        return {"current_year": datetime.now().year, "company_logo_url": logo_url,
                "system_name": system_name, "ubicaciones": ubicaciones,
                "ubicacion_label": ubicacion_label, "stock_en": stock_en}

    # =================================================================
    # SEGURIDAD: cabeceras HTTP, proteccion CSRF y anti-fijacion de sesion
    # =================================================================
    import secrets
    from flask import request, session

    # Endpoints que aceptan POST sin token CSRF (login: evita problemas de cache PWA)
    CSRF_EXENTOS = {"auth.login"}

    @app.before_request
    def _proteger_csrf():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.endpoint in CSRF_EXENTOS:
                return
            token = session.get("csrf_token")
            enviado = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
            if not token or not enviado or not secrets.compare_digest(str(token), str(enviado)):
                return render_template_error(
                    "Token de seguridad inválido o expirado. Recarga la página (F5) e inténtalo de nuevo.", 400
                )

    @app.context_processor
    def _inyectar_csrf():
        tok = session.get("csrf_token")
        if not tok:
            tok = secrets.token_urlsafe(32)
            session["csrf_token"] = tok
        return {"csrf_token": tok}

    @app.after_request
    def _cabeceras_seguridad(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: blob: https://api.qrserver.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            "connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; "
            "form-action 'self'; object-src 'none'",
        )
        if app.config.get("BEHIND_PROXY"):
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

    return app


def render_template_error(message, code):
    from flask import render_template
    return render_template("error.html", message=message), code
