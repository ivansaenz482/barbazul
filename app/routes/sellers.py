from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models import Seller
from app.utils import role_required

sellers_bp = Blueprint("sellers", __name__, url_prefix="/vendedores")


@sellers_bp.route("/")
@login_required
@role_required("administrador")
def sellers_list():
    q = request.args.get("q", "").strip()
    query = Seller.query
    if q:
        query = query.filter(Seller.name.ilike(f"%{q}%"))
    sellers = query.order_by(Seller.name).all()
    return render_template("sellers_list.html", sellers=sellers, q=q)


@sellers_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def seller_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("El nombre del vendedor es obligatorio.", "danger")
            return render_template("seller_form.html", seller=None)

        db.session.add(Seller(
            name=name,
            phone=request.form.get("phone", "").strip() or None,
            commission_percent=float(request.form.get("commission_percent") or 0),
            active=True,
        ))
        db.session.commit()
        flash(f"Vendedor '{name}' registrado correctamente.", "success")
        return redirect(url_for("sellers.sellers_list"))

    return render_template("seller_form.html", seller=None)


@sellers_bp.route("/<int:seller_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def seller_edit(seller_id):
    seller = Seller.query.get_or_404(seller_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("El nombre del vendedor es obligatorio.", "danger")
            return render_template("seller_form.html", seller=seller)

        seller.name = name
        seller.phone = request.form.get("phone", "").strip() or None
        seller.commission_percent = float(request.form.get("commission_percent") or 0)
        seller.active = request.form.get("active") == "on"
        db.session.commit()
        flash("Vendedor actualizado.", "success")
        return redirect(url_for("sellers.sellers_list"))

    return render_template("seller_form.html", seller=seller)


@sellers_bp.route("/<int:seller_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def seller_delete(seller_id):
    seller = Seller.query.get_or_404(seller_id)
    seller.active = False  # borrado logico: conserva historial de ventas
    db.session.commit()
    flash(f"Vendedor '{seller.name}' desactivado.", "info")
    return redirect(url_for("sellers.sellers_list"))
