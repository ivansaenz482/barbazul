from flask import Blueprint, jsonify, render_template, redirect, url_for, current_app, send_from_directory
from flask_login import login_required, current_user
from app.models import Product, Customer, Role

main_bp = Blueprint("main", __name__)


@main_bp.route("/manifest.webmanifest")
def manifest():
    resp = send_from_directory(current_app.static_folder, "manifest.webmanifest",
                               mimetype="application/manifest+json")
    return resp


@main_bp.route("/sw.js")
def service_worker():
    resp = send_from_directory(current_app.static_folder, "sw.js",
                               mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_admin():
        return render_template("dashboard_admin.html", user=current_user)
    return render_template("dashboard_personal.html", user=current_user)


@main_bp.route("/test-db")
def test_db():
    """Ruta temporal para confirmar que Flask esta leyendo la base de datos MySQL"""
    try:
        total_productos = Product.query.count()
        total_clientes = Customer.query.count()
        roles = [r.role_name for r in Role.query.all()]
        return jsonify({
            "estado": "conexion exitosa",
            "productos_en_bd": total_productos,
            "clientes_en_bd": total_clientes,
            "roles_configurados": roles
        })
    except Exception as e:
        return jsonify({"estado": "error", "detalle": str(e)}), 500
