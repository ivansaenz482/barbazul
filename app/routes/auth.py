import secrets
from datetime import datetime, timedelta

import bcrypt
from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db
from app.models import User, AuditLog
from app.audit import registrar

auth_bp = Blueprint("auth", __name__)

# Proteccion contra fuerza bruta: maximo de intentos fallidos por ventana de tiempo
MAX_INTENTOS = 5
VENTANA_MIN = 15


def _registrar_fallo(username, ip):
    """Guarda un intento de login fallido (para auditoria y bloqueo temporal)."""
    try:
        db.session.add(AuditLog(
            username=(username or None),
            accion="login_fallido",
            detalle=f"Intento fallido con usuario '{username or '(vacío)'}'",
            ip=ip or None,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _esta_bloqueado(username, ip):
    """True si esa IP o ese usuario acumularon demasiados fallos recientes."""
    desde = datetime.now() - timedelta(minutes=VENTANA_MIN)
    por_ip = 0
    por_usuario = 0
    if ip:
        por_ip = AuditLog.query.filter(
            AuditLog.accion == "login_fallido",
            AuditLog.created_at >= desde,
            AuditLog.ip == ip,
        ).count()
    if username:
        por_usuario = AuditLog.query.filter(
            AuditLog.accion == "login_fallido",
            AuditLog.created_at >= desde,
            AuditLog.username == username,
        ).count()
    return por_ip >= MAX_INTENTOS or por_usuario >= MAX_INTENTOS


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        ip = request.remote_addr or ""

        if _esta_bloqueado(username, ip):
            flash(f"Demasiados intentos fallidos. Por seguridad, espera {VENTANA_MIN} minutos e intenta de nuevo.", "danger")
            return render_template("login.html")

        user = User.query.filter_by(username=username).first()

        credencial_valida = False
        if user and user.active and user.password_hash:
            try:
                credencial_valida = bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8"))
            except (ValueError, TypeError):
                credencial_valida = False

        if credencial_valida:
            # Evita la fijacion de sesion: se limpia y se regenera un token nuevo.
            session.clear()
            login_user(user)
            session["csrf_token"] = secrets.token_urlsafe(32)
            registrar("login", detalle=f"Ingreso de {user.username}", entidad="usuario", entidad_id=user.user_id)
            flash(f"Bienvenido, {user.full_name}", "success")
            return redirect(url_for("main.dashboard"))

        _registrar_fallo(username, ip)
        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    registrar("logout", detalle=f"Salida de {current_user.username}", entidad="usuario", entidad_id=current_user.user_id)
    logout_user()
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))
