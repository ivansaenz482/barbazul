from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.extensions import db
from app.models import Customer, Branch
from app.utils import role_required, perm_required
from app.geo_data import PROVINCIAS_ECUADOR, CIUDADES_PRINCIPALES

customers_bp = Blueprint("customers", __name__, url_prefix="/clientes")


# =====================================================================
# LOCALES / SUCURSALES
# =====================================================================

@customers_bp.route("/locales")
@login_required
@perm_required("can_view_clientes")
def branches_list():
    branches = Branch.query.order_by(Branch.name).all()
    return render_template("branches_list.html", branches=branches)


@customers_bp.route("/locales/nuevo", methods=["GET", "POST"])
@login_required
@perm_required("can_view_clientes")
def branch_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("El nombre del local es obligatorio.", "danger")
            return render_template("branch_form.html", branch=None)

        db.session.add(Branch(
            name=name,
            address=request.form.get("address", "").strip() or None,
            phone=request.form.get("phone", "").strip() or None,
        ))
        db.session.commit()
        flash("Local creado correctamente.", "success")
        return redirect(url_for("customers.branches_list"))

    return render_template("branch_form.html", branch=None)


@customers_bp.route("/locales/<int:branch_id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("can_view_clientes")
def branch_edit(branch_id):
    branch = Branch.query.get_or_404(branch_id)

    if request.method == "POST":
        branch.name = request.form.get("name", "").strip()
        branch.address = request.form.get("address", "").strip() or None
        branch.phone = request.form.get("phone", "").strip() or None
        db.session.commit()
        flash("Local actualizado.", "success")
        return redirect(url_for("customers.branches_list"))

    return render_template("branch_form.html", branch=branch)


@customers_bp.route("/locales/<int:branch_id>/eliminar", methods=["POST"])
@login_required
@perm_required("can_view_clientes")
def branch_delete(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    if branch.customers:
        flash("No puedes eliminar un local que tiene clientes asociados.", "danger")
    else:
        db.session.delete(branch)
        db.session.commit()
        flash("Local eliminado.", "info")
    return redirect(url_for("customers.branches_list"))


# =====================================================================
# CLIENTES
# =====================================================================



@customers_bp.route("/")
@login_required
@perm_required("can_view_clientes")
def customers_list():
    search = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "").strip()
    branch_id = request.args.get("branch_id", "").strip()

    query = Customer.query
    if search:
        query = query.filter(
            (Customer.full_name.ilike(f"%{search}%")) | (Customer.cedula.ilike(f"%{search}%"))
        )
    if tipo in ("efectivo", "credito"):
        query = query.filter(Customer.customer_type == tipo)
    if branch_id:
        query = query.filter(Customer.branch_id == int(branch_id))

    customers = query.order_by(Customer.full_name).all()
    branches = Branch.query.filter_by(active=True).order_by(Branch.name).all()
    return render_template("customers_list.html", customers=customers, search=search, tipo=tipo,
                            branches=branches, branch_id=branch_id)


@customers_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@perm_required("can_view_clientes")
def customer_new():
    branches = Branch.query.filter_by(active=True).order_by(Branch.name).all()

    if request.method == "POST":
        cedula = request.form.get("cedula", "").strip() or None
        full_name = request.form.get("full_name", "").strip()

        if not full_name:
            flash("El nombre del cliente es obligatorio.", "danger")
            return render_template("customer_form.html", customer=None, branches=branches,
                                    provincias=PROVINCIAS_ECUADOR, ciudades=CIUDADES_PRINCIPALES)

        if cedula and Customer.query.filter_by(cedula=cedula).first():
            flash(f"Ya existe un cliente con la cédula '{cedula}'.", "danger")
            return render_template("customer_form.html", customer=None, branches=branches,
                                    provincias=PROVINCIAS_ECUADOR, ciudades=CIUDADES_PRINCIPALES)

        customer_type = request.form.get("customer_type", "efectivo")
        credit_term_days = request.form.get("credit_term_days", "0") if customer_type == "credito" else "0"
        price_list = request.form.get("price_list", "contado")
        if price_list not in ("contado", "credito", "mayorista"):
            price_list = "contado"

        customer = Customer(
            cedula=cedula,
            full_name=full_name,
            business_name=request.form.get("business_name", "").strip() or None,
            phone=request.form.get("phone", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            address=request.form.get("address", "").strip() or None,
            province=request.form.get("province", "").strip() or None,
            city=request.form.get("city", "").strip() or None,
            customer_type=customer_type,
            price_list=price_list,
            credit_limit=float(request.form.get("credit_limit") or 0) if customer_type == "credito" else 0,
            credit_term_days=credit_term_days,
            branch_id=request.form.get("branch_id") or None,
            active=True,
        )
        db.session.add(customer)
        db.session.commit()
        flash(f"Cliente '{full_name}' registrado correctamente.", "success")
        return redirect(url_for("customers.customers_list"))

    return render_template("customer_form.html", customer=None, branches=branches,
                            provincias=PROVINCIAS_ECUADOR, ciudades=CIUDADES_PRINCIPALES)


@customers_bp.route("/<int:customer_id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("can_view_clientes")
def customer_edit(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    branches = Branch.query.filter_by(active=True).order_by(Branch.name).all()

    if request.method == "POST":
        cedula = request.form.get("cedula", "").strip() or None
        if cedula and cedula != customer.cedula and Customer.query.filter_by(cedula=cedula).first():
            flash(f"Ya existe otro cliente con la cédula '{cedula}'.", "danger")
            return render_template("customer_form.html", customer=customer, branches=branches,
                                    provincias=PROVINCIAS_ECUADOR, ciudades=CIUDADES_PRINCIPALES)

        customer_type = request.form.get("customer_type", "efectivo")

        customer.cedula = cedula
        customer.full_name = request.form.get("full_name", "").strip()
        customer.business_name = request.form.get("business_name", "").strip() or None
        customer.phone = request.form.get("phone", "").strip() or None
        customer.email = request.form.get("email", "").strip() or None
        customer.address = request.form.get("address", "").strip() or None
        customer.province = request.form.get("province", "").strip() or None
        customer.city = request.form.get("city", "").strip() or None
        customer.customer_type = customer_type
        price_list = request.form.get("price_list", "contado")
        if price_list not in ("contado", "credito", "mayorista"):
            price_list = "contado"
        customer.price_list = price_list
        customer.credit_limit = float(request.form.get("credit_limit") or 0) if customer_type == "credito" else 0
        customer.credit_term_days = request.form.get("credit_term_days", "0") if customer_type == "credito" else "0"
        customer.branch_id = request.form.get("branch_id") or None
        db.session.commit()
        flash("Cliente actualizado.", "success")
        return redirect(url_for("customers.customers_list"))

    return render_template("customer_form.html", customer=customer, branches=branches,
                            provincias=PROVINCIAS_ECUADOR, ciudades=CIUDADES_PRINCIPALES)


@customers_bp.route("/<int:customer_id>/eliminar", methods=["POST"])
@login_required
@perm_required("can_view_clientes")
def customer_delete(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.active = False  # borrado logico: conserva historial de ventas
    db.session.commit()
    flash(f"Cliente '{customer.full_name}' desactivado.", "info")
    return redirect(url_for("customers.customers_list"))
