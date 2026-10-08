import os
import uuid

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, send_file, abort)
from flask_login import login_required
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import CompanySetting
from app.utils import role_required, resolver_ruta_upload

settings_bp = Blueprint("settings", __name__, url_prefix="/configuracion")


def _allowed_logo(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_LOGO_EXTENSIONS"]


@settings_bp.route("/")
@login_required
@role_required("administrador")
def settings_page():
    company = CompanySetting.actual()
    return render_template("settings_page.html", company=company)


@settings_bp.route("/nombre", methods=["POST"])
@login_required
@role_required("administrador")
def save_name():
    company = CompanySetting.actual()
    if not company:
        company = CompanySetting()
        db.session.add(company)
    company.system_name = request.form.get("system_name", "").strip() or None
    db.session.commit()
    flash("Nombre del sistema actualizado.", "success")
    return redirect(url_for("settings.settings_page"))


@settings_bp.route("/logo", methods=["GET"])
@login_required
def company_logo():
    company = CompanySetting.actual()
    ruta = resolver_ruta_upload(company.logo_path, current_app.config["LOGO_FOLDER"]) if company else None
    if not ruta:
        abort(404)
    return send_file(ruta)


@settings_bp.route("/logo/subir", methods=["POST"])
@login_required
@role_required("administrador")
def logo_upload():
    file = request.files.get("logo")
    if not file or not file.filename:
        flash("Selecciona una imagen para el logo.", "danger")
        return redirect(url_for("settings.settings_page"))

    if not _allowed_logo(file.filename):
        flash("Formato no permitido. Usa PNG, JPG, JPEG, WEBP o GIF.", "danger")
        return redirect(url_for("settings.settings_page"))

    os.makedirs(current_app.config["LOGO_FOLDER"], exist_ok=True)
    filename = secure_filename(file.filename)
    unique_name = f"logo_{uuid.uuid4().hex}_{filename}"
    save_path = os.path.join(current_app.config["LOGO_FOLDER"], unique_name)
    file.save(save_path)

    company = CompanySetting.actual()
    if not company:
        company = CompanySetting()
        db.session.add(company)

    if company.logo_path and os.path.exists(company.logo_path):
        try:
            os.remove(company.logo_path)
        except OSError:
            pass

    company.logo_path = save_path
    db.session.commit()
    flash("Logo actualizado correctamente.", "success")
    return redirect(url_for("settings.settings_page"))


@settings_bp.route("/logo/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def logo_delete():
    company = CompanySetting.actual()
    if company and company.logo_path:
        if os.path.exists(company.logo_path):
            try:
                os.remove(company.logo_path)
            except OSError:
                pass
        company.logo_path = None
        db.session.commit()
        flash("Logo eliminado.", "info")
    return redirect(url_for("settings.settings_page"))
