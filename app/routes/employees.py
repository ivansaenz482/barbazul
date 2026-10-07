from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models import Employee
from app.utils import role_required

employees_bp = Blueprint("employees", __name__, url_prefix="/personal")

ROLES = [("vendedor", "Vendedor"), ("chofer", "Chofer"),
         ("administrador", "Administrador"), ("bodeguero", "Bodeguero"), ("otro", "Otro")]


@employees_bp.route("/")
@login_required
@role_required("administrador")
def employees_list():
    q = request.args.get("q", "").strip()
    query = Employee.query
    if q:
        query = query.filter(Employee.name.ilike(f"%{q}%"))
    employees = query.order_by(Employee.name).all()
    return render_template("employees_list.html", employees=employees, q=q)


@employees_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def employee_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("El nombre es obligatorio.", "danger")
            return render_template("employee_form.html", employee=None, roles=ROLES)

        role = request.form.get("role", "vendedor")
        if role not in [r[0] for r in ROLES]:
            role = "otro"

        db.session.add(Employee(
            name=name,
            role=role,
            phone=request.form.get("phone", "").strip() or None,
            base_salary=float(request.form.get("base_salary") or 0),
            active=True,
        ))
        db.session.commit()
        flash(f"'{name}' agregado al personal.", "success")
        return redirect(url_for("employees.employees_list"))

    return render_template("employee_form.html", employee=None, roles=ROLES)


@employees_bp.route("/<int:employee_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def employee_edit(employee_id):
    employee = Employee.query.get_or_404(employee_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("El nombre es obligatorio.", "danger")
            return render_template("employee_form.html", employee=employee, roles=ROLES)

        role = request.form.get("role", employee.role)
        if role not in [r[0] for r in ROLES]:
            role = employee.role

        employee.name = name
        employee.role = role
        employee.phone = request.form.get("phone", "").strip() or None
        employee.base_salary = float(request.form.get("base_salary") or 0)
        employee.active = request.form.get("active") == "on"
        db.session.commit()
        flash("Personal actualizado.", "success")
        return redirect(url_for("employees.employees_list"))

    return render_template("employee_form.html", employee=employee, roles=ROLES)


@employees_bp.route("/<int:employee_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def employee_delete(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    employee.active = False
    db.session.commit()
    flash(f"'{employee.name}' desactivado.", "info")
    return redirect(url_for("employees.employees_list"))
