import os
import uuid
import bcrypt
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import User, Category, Role
from app.utils import role_required, resolver_ruta_upload

users_bp = Blueprint("users", __name__, url_prefix="/usuarios")


@users_bp.route("/")
@login_required
@role_required("administrador")
def users_list():
    users = User.query.order_by(User.full_name).all()
    return render_template("users_list.html", users=users)


@users_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def user_new():
    roles = Role.query.order_by(Role.role_name).all()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        role_id = request.form.get("role_id")
        bodega = request.form.get("bodega") or None
        if bodega not in ("local", "matriz"):
            bodega = None

        if not username or not full_name or not password or not role_id:
            flash("Completa usuario, nombre completo, contraseña y rol.", "danger")
            return render_template("user_form.html", roles=roles, user=None)

        if User.query.filter_by(username=username).first():
            flash(f"Ya existe un usuario con el nombre '{username}'.", "danger")
            return render_template("user_form.html", roles=roles, user=None)

        if password != password_confirm:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("user_form.html", roles=roles, user=None)

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "danger")
            return render_template("user_form.html", roles=roles, user=None)

        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        new_user = User(
            username=username,
            password_hash=password_hash,
            full_name=full_name,
            email=email or None,
            phone=phone or None,
            role_id=int(role_id),
            bodega=bodega,
            active=True,
        )
        db.session.add(new_user)
        db.session.commit()
        flash(f"Usuario '{username}' creado correctamente.", "success")
        return redirect(url_for("users.users_list"))

    return render_template("user_form.html", roles=roles, user=None)


@users_bp.route("/<int:user_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
    roles = Role.query.order_by(Role.role_name).all()

    if request.method == "POST":
        es_uno_mismo = (user.user_id == current_user.user_id)
        nuevo_role_id = int(request.form.get("role_id"))
        nuevo_activo = request.form.get("active") == "on"

        # Evitar que el administrador se bloquee o se quite su propio rol sin querer
        if es_uno_mismo:
            if not nuevo_activo:
                flash("No puedes desactivar tu propio usuario.", "danger")
                return render_template("user_form.html", roles=roles, user=user)
            nuevo_role = Role.query.get(nuevo_role_id)
            if nuevo_role.role_name != "administrador":
                flash("No puedes quitarte tu propio rol de administrador.", "danger")
                return render_template("user_form.html", roles=roles, user=user)

        user.full_name = request.form.get("full_name", "").strip()
        user.email = request.form.get("email", "").strip() or None
        user.phone = request.form.get("phone", "").strip() or None
        user.role_id = nuevo_role_id
        bodega = request.form.get("bodega") or None
        user.bodega = bodega if bodega in ("local", "matriz") else None
        user.active = nuevo_activo

        new_password = request.form.get("password", "")
        if new_password:
            if len(new_password) < 6:
                flash("La nueva contraseña debe tener al menos 6 caracteres.", "danger")
                return render_template("user_form.html", roles=roles, user=user)
            user.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        db.session.commit()
        flash(f"Usuario '{user.username}' actualizado correctamente.", "success")
        return redirect(url_for("users.users_list"))

    return render_template("user_form.html", roles=roles, user=user)


@users_bp.route("/<int:user_id>/permisos", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def user_permisos_edit(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin():
        flash("Los administradores ya tienen todos los permisos automáticamente.", "info")
        return redirect(url_for("users.users_list"))

    if request.method == "POST":
        user.perm_inventario = request.form.get("perm_inventario") == "on"
        user.perm_ventas = request.form.get("perm_ventas") == "on"
        user.perm_clientes = request.form.get("perm_clientes") == "on"
        user.perm_edit_stock = request.form.get("perm_edit_stock") == "on"
        user.perm_edit_pedidos = request.form.get("perm_edit_pedidos") == "on"
        user.perm_reporte_caja = request.form.get("perm_reporte_caja") == "on"
        db.session.commit()
        flash(f"Permisos de '{user.full_name}' actualizados correctamente.", "success")
        return redirect(url_for("users.users_list"))

    return render_template("user_permisos_form.html", user=user)


@users_bp.route("/<int:user_id>/categorias", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def user_categories_edit(user_id):
    user = User.query.get_or_404(user_id)
    categories = Category.query.order_by(Category.name).all()

    if user.is_admin():
        flash("Los administradores ya tienen acceso a todas las categorías; no aplica restricción.", "info")
        return redirect(url_for("users.users_list"))

    if request.method == "POST":
        selected_ids = request.form.getlist("category_ids[]")
        user.allowed_categories = Category.query.filter(Category.category_id.in_(selected_ids)).all()
        db.session.commit()

        if selected_ids:
            flash(f"'{user.full_name}' ahora solo puede vender {len(selected_ids)} categoría(s) seleccionada(s).", "success")
        else:
            flash(f"'{user.full_name}' puede vender de todas las categorías (sin restricción).", "success")

        return redirect(url_for("users.users_list"))

    return render_template("user_categories_form.html", user=user, categories=categories)


# =====================================================================
# MI PERFIL (foto y datos propios — cualquier usuario logueado)
# =====================================================================

def _allowed_avatar(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_AVATAR_EXTENSIONS"]


@users_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def mi_perfil():
    if request.method == "POST":
        current_user.full_name = request.form.get("full_name", "").strip() or current_user.full_name
        current_user.email = request.form.get("email", "").strip() or None
        current_user.phone = request.form.get("phone", "").strip() or None

        new_password = request.form.get("password", "")
        if new_password:
            if len(new_password) < 6:
                flash("La nueva contraseña debe tener al menos 6 caracteres.", "danger")
                return render_template("profile.html", user=current_user)
            current_user.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        file = request.files.get("avatar")
        if file and file.filename:
            if not _allowed_avatar(file.filename):
                flash("Formato de imagen no permitido. Usa PNG, JPG o JPEG.", "danger")
                return render_template("profile.html", user=current_user)

            os.makedirs(current_app.config["AVATAR_FOLDER"], exist_ok=True)
            filename = secure_filename(file.filename)
            unique_name = f"user{current_user.user_id}_{uuid.uuid4().hex}_{filename}"
            save_path = os.path.join(current_app.config["AVATAR_FOLDER"], unique_name)
            file.save(save_path)

            # Borra la foto anterior para no acumular archivos
            if current_user.avatar_path and os.path.exists(current_user.avatar_path):
                try:
                    os.remove(current_user.avatar_path)
                except OSError:
                    pass

            current_user.avatar_path = save_path

        db.session.commit()
        flash("Perfil actualizado correctamente.", "success")
        return redirect(url_for("users.mi_perfil"))

    return render_template("profile.html", user=current_user)


@users_bp.route("/avatar/<int:user_id>")
@login_required
def user_avatar(user_id):
    user = User.query.get_or_404(user_id)
    ruta = resolver_ruta_upload(user.avatar_path, current_app.config["AVATAR_FOLDER"])
    if not ruta:
        abort(404)
    return send_file(ruta)
