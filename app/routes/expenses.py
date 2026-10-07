from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Expense, Employee
from app.utils import role_required

expenses_bp = Blueprint("expenses", __name__, url_prefix="/gastos")

CATEGORIAS = [
    ("sueldos", "Sueldos / Personal"),
    ("luz", "Luz"),
    ("arriendo", "Arriendo"),
    ("agua", "Agua"),
    ("internet", "Internet"),
    ("transporte", "Transporte"),
    ("otros", "Otros"),
]
CATEGORIA_KEYS = [c[0] for c in CATEGORIAS]
METODOS = ["efectivo", "transferencia", "cheque", "otro"]


def _datos_form():
    """Lee y valida los campos del formulario. Devuelve (datos, error)."""
    try:
        expense_date = datetime.strptime(request.form.get("expense_date", ""), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        expense_date = date.today()

    category = request.form.get("category", "otros")
    if category not in CATEGORIA_KEYS:
        category = "otros"

    try:
        amount = float(request.form.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return None, "El monto del gasto debe ser mayor a cero."

    payment_method = request.form.get("payment_method", "efectivo")
    if payment_method not in METODOS:
        payment_method = "efectivo"

    employee_id = request.form.get("employee_id") or None
    if category != "sueldos":
        employee_id = None

    return {
        "expense_date": expense_date,
        "category": category,
        "description": request.form.get("description", "").strip() or None,
        "amount": amount,
        "employee_id": int(employee_id) if employee_id else None,
        "payment_method": payment_method,
    }, None


@expenses_bp.route("/")
@login_required
@role_required("administrador")
def expenses_list():
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()
    categoria = request.args.get("categoria", "").strip()

    query = Expense.query
    if categoria in CATEGORIA_KEYS:
        query = query.filter(Expense.category == categoria)
    if desde:
        try:
            query = query.filter(Expense.expense_date >= datetime.strptime(desde, "%Y-%m-%d").date())
        except ValueError:
            pass
    if hasta:
        try:
            query = query.filter(Expense.expense_date <= datetime.strptime(hasta, "%Y-%m-%d").date())
        except ValueError:
            pass

    gastos = query.order_by(Expense.expense_date.desc(), Expense.expense_id.desc()).all()
    total = sum(float(g.amount) for g in gastos)

    return render_template("expenses_list.html", gastos=gastos, total=total,
                           categorias=CATEGORIAS, desde=desde, hasta=hasta,
                           selected_categoria=categoria)


@expenses_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def expense_new():
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()
    # Prellenado (ej. al registrar el pago de un empleado desde Personal)
    pre_emp = request.args.get("employee_id", "")
    pre_cat = request.args.get("category", "")

    if request.method == "POST":
        datos, error = _datos_form()
        if error:
            flash(error, "danger")
            return render_template("expense_form.html", expense=None, employees=employees,
                                   categorias=CATEGORIAS, metodos=METODOS)

        gasto = Expense(created_by=current_user.user_id, **datos)
        db.session.add(gasto)
        db.session.commit()
        flash(f"Gasto de ${datos['amount']:.2f} registrado.", "success")
        return redirect(url_for("expenses.expenses_list"))

    return render_template("expense_form.html", expense=None, employees=employees,
                           categorias=CATEGORIAS, metodos=METODOS, today=date.today().isoformat(),
                           pre_emp=pre_emp, pre_cat=pre_cat)


@expenses_bp.route("/<int:expense_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def expense_edit(expense_id):
    gasto = Expense.query.get_or_404(expense_id)
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()

    if request.method == "POST":
        datos, error = _datos_form()
        if error:
            flash(error, "danger")
            return render_template("expense_form.html", expense=gasto, employees=employees,
                                   categorias=CATEGORIAS, metodos=METODOS)

        for campo, valor in datos.items():
            setattr(gasto, campo, valor)
        db.session.commit()
        flash("Gasto actualizado.", "success")
        return redirect(url_for("expenses.expenses_list"))

    return render_template("expense_form.html", expense=gasto, employees=employees,
                           categorias=CATEGORIAS, metodos=METODOS)


@expenses_bp.route("/<int:expense_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def expense_delete(expense_id):
    gasto = Expense.query.get_or_404(expense_id)
    monto = float(gasto.amount)
    db.session.delete(gasto)
    db.session.commit()
    flash(f"Gasto de ${monto:.2f} eliminado.", "info")
    return redirect(url_for("expenses.expenses_list"))
