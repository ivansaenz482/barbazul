import os
from flask import Blueprint, render_template, redirect, url_for, flash, send_file, abort
from flask_login import login_required
from werkzeug.utils import secure_filename

from app.backup_utils import create_backup, list_backups, _backup_folder
from app.utils import role_required

backups_bp = Blueprint("backups", __name__, url_prefix="/respaldos")


@backups_bp.route("/")
@login_required
@role_required("administrador")
def backups_page():
    backups = list_backups()
    return render_template("backups_page.html", backups=backups)


@backups_bp.route("/nuevo", methods=["POST"])
@login_required
@role_required("administrador")
def backup_new():
    ok, mensaje, _ = create_backup()
    flash(mensaje, "success" if ok else "danger")
    return redirect(url_for("backups.backups_page"))


@backups_bp.route("/<path:filename>/descargar")
@login_required
@role_required("administrador")
def backup_download(filename):
    filename = secure_filename(filename)
    folder = _backup_folder()
    filepath = os.path.join(folder, filename)

    # Evitar descargar archivos fuera de la carpeta de respaldos
    if not os.path.abspath(filepath).startswith(os.path.abspath(folder)) or not os.path.isfile(filepath):
        abort(404)

    return send_file(filepath, as_attachment=True, download_name=filename)


@backups_bp.route("/<path:filename>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def backup_delete(filename):
    filename = secure_filename(filename)
    folder = _backup_folder()
    filepath = os.path.join(folder, filename)

    if os.path.abspath(filepath).startswith(os.path.abspath(folder)) and os.path.isfile(filepath):
        os.remove(filepath)
        flash(f"Respaldo '{filename}' eliminado.", "info")
    else:
        flash("Ese respaldo no existe.", "danger")

    return redirect(url_for("backups.backups_page"))
