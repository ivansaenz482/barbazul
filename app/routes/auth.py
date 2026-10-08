import bcrypt
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app.audit import registrar

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user and user.active and bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            login_user(user)
            registrar("login", detalle=f"Ingreso de {user.username}", entidad="usuario", entidad_id=user.user_id)
            flash(f"Bienvenido, {user.full_name}", "success")
            return redirect(url_for("main.dashboard"))

        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    registrar("logout", detalle=f"Salida de {current_user.username}", entidad="usuario", entidad_id=current_user.user_id)
    logout_user()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))
