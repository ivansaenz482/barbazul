from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Employee, Expense, Attendance, LeaveRequest, Advance
from app.utils import role_required

hr_bp = Blueprint("hr", __name__, url_prefix="/rrhh")

LEAVE_TYPES = [("vacaciones", "Vacaciones"), ("permiso", "Permiso"),
               ("enfermedad", "Enfermedad"), ("otro", "Otro")]


def _employees():
    return Employee.query.filter_by(active=True).order_by(Employee.name).all()


def _parse_time(valor):
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%H:%M").time()
    except ValueError:
        return None


def _parse_date(valor):
    try:
        return datetime.strptime((valor or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# =====================================================================
# RESUMEN
# =====================================================================

@hr_bp.route("/")
@login_required
@role_required("administrador")
def hr_home():
    total_personal = Employee.query.filter_by(active=True).count()
    asistencia_hoy = Attendance.query.filter_by(date=date.today()).count()
    vacaciones_pend = LeaveRequest.query.filter_by(status="pendiente").count()
    adelantos_pend = Advance.query.filter_by(status="pendiente").count()
    return render_template("hr_home.html",
                           total_personal=total_personal,
                           asistencia_hoy=asistencia_hoy,
                           vacaciones_pend=vacaciones_pend,
                           adelantos_pend=adelantos_pend)


# =====================================================================
# ASISTENCIA
# =====================================================================

@hr_bp.route("/asistencia")
@login_required
@role_required("administrador")
def hr_asistencia():
    employee_id = request.args.get("employee_id", "").strip()
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()

    query = Attendance.query
    if employee_id:
        query = query.filter(Attendance.employee_id == int(employee_id))
    if desde:
        query = query.filter(Attendance.date >= _parse_date(desde))
    if hasta:
        query = query.filter(Attendance.date <= _parse_date(hasta))

    registros = query.order_by(Attendance.date.desc(), Attendance.attendance_id.desc()).limit(300).all()
    return render_template("hr_asistencia.html", registros=registros, employees=_employees(),
                           selected_employee=employee_id, desde=desde, hasta=hasta, today=date.today().isoformat())


@hr_bp.route("/asistencia/nueva", methods=["POST"])
@login_required
@role_required("administrador")
def hr_asistencia_nueva():
    employee = Employee.query.get(request.form.get("employee_id")) if request.form.get("employee_id") else None
    fecha = _parse_date(request.form.get("date")) or date.today()
    if not employee:
        flash("Selecciona un empleado.", "danger")
        return redirect(url_for("hr.hr_asistencia"))

    db.session.add(Attendance(
        employee_id=employee.employee_id,
        date=fecha,
        check_in=_parse_time(request.form.get("check_in")),
        check_out=_parse_time(request.form.get("check_out")),
        notes=request.form.get("notes", "").strip() or None,
        created_by=current_user.user_id,
    ))
    db.session.commit()
    flash("Asistencia registrada.", "success")
    return redirect(url_for("hr.hr_asistencia"))


@hr_bp.route("/asistencia/<int:reg_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def hr_asistencia_eliminar(reg_id):
    reg = Attendance.query.get_or_404(reg_id)
    db.session.delete(reg)
    db.session.commit()
    flash("Registro de asistencia eliminado.", "info")
    return redirect(url_for("hr.hr_asistencia"))


# =====================================================================
# VACACIONES Y PERMISOS
# =====================================================================

@hr_bp.route("/vacaciones")
@login_required
@role_required("administrador")
def hr_vacaciones():
    registros = LeaveRequest.query.order_by(LeaveRequest.start_date.desc(), LeaveRequest.leave_id.desc()).limit(300).all()
    return render_template("hr_vacaciones.html", registros=registros, employees=_employees(),
                           tipos=LEAVE_TYPES, today=date.today().isoformat())


@hr_bp.route("/vacaciones/nueva", methods=["POST"])
@login_required
@role_required("administrador")
def hr_vacaciones_nueva():
    employee = Employee.query.get(request.form.get("employee_id")) if request.form.get("employee_id") else None
    start = _parse_date(request.form.get("start_date"))
    end = _parse_date(request.form.get("end_date")) or start
    tipo = request.form.get("type", "permiso")
    if tipo not in [t[0] for t in LEAVE_TYPES]:
        tipo = "permiso"
    if not employee or not start:
        flash("Selecciona el empleado y la fecha de inicio.", "danger")
        return redirect(url_for("hr.hr_vacaciones"))
    if end < start:
        end = start

    db.session.add(LeaveRequest(
        employee_id=employee.employee_id, type=tipo,
        start_date=start, end_date=end,
        reason=request.form.get("reason", "").strip() or None,
        status="pendiente", created_by=current_user.user_id,
    ))
    db.session.commit()
    flash("Solicitud registrada.", "success")
    return redirect(url_for("hr.hr_vacaciones"))


@hr_bp.route("/vacaciones/<int:leave_id>/estado", methods=["POST"])
@login_required
@role_required("administrador")
def hr_vacaciones_estado(leave_id):
    reg = LeaveRequest.query.get_or_404(leave_id)
    nuevo = request.form.get("status", "")
    if nuevo in ("pendiente", "aprobado", "rechazado"):
        reg.status = nuevo
        db.session.commit()
        flash(f"Solicitud {reg.status_label()}.", "success")
    return redirect(url_for("hr.hr_vacaciones"))


@hr_bp.route("/vacaciones/<int:leave_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def hr_vacaciones_eliminar(leave_id):
    db.session.delete(LeaveRequest.query.get_or_404(leave_id))
    db.session.commit()
    flash("Solicitud eliminada.", "info")
    return redirect(url_for("hr.hr_vacaciones"))


# =====================================================================
# ADELANTOS Y PRESTAMOS
# =====================================================================

@hr_bp.route("/adelantos")
@login_required
@role_required("administrador")
def hr_adelantos():
    registros = Advance.query.order_by(Advance.date.desc(), Advance.advance_id.desc()).limit(300).all()
    total_pend = sum(float(a.amount) for a in registros if a.status == "pendiente")
    return render_template("hr_adelantos.html", registros=registros, employees=_employees(),
                           total_pendiente=total_pend, today=date.today().isoformat())


@hr_bp.route("/adelantos/nuevo", methods=["POST"])
@login_required
@role_required("administrador")
def hr_adelantos_nuevo():
    employee = Employee.query.get(request.form.get("employee_id")) if request.form.get("employee_id") else None
    fecha = _parse_date(request.form.get("date")) or date.today()
    try:
        monto = float(request.form.get("amount") or 0)
    except (TypeError, ValueError):
        monto = 0
    kind = request.form.get("kind", "adelanto")
    if kind not in ("adelanto", "prestamo"):
        kind = "adelanto"
    if not employee or monto <= 0:
        flash("Selecciona el empleado y un monto mayor a cero.", "danger")
        return redirect(url_for("hr.hr_adelantos"))

    db.session.add(Advance(
        employee_id=employee.employee_id, date=fecha, amount=monto, kind=kind,
        description=request.form.get("description", "").strip() or None,
        status="pendiente", created_by=current_user.user_id,
    ))
    db.session.commit()
    flash(f"{'Adelanto' if kind == 'adelanto' else 'Préstamo'} registrado.", "success")
    return redirect(url_for("hr.hr_adelantos"))


@hr_bp.route("/adelantos/<int:adv_id>/estado", methods=["POST"])
@login_required
@role_required("administrador")
def hr_adelantos_estado(adv_id):
    reg = Advance.query.get_or_404(adv_id)
    reg.status = "descontado" if reg.status == "pendiente" else "pendiente"
    db.session.commit()
    flash(f"Marcado como {reg.status_label()}.", "success")
    return redirect(url_for("hr.hr_adelantos"))


@hr_bp.route("/adelantos/<int:adv_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def hr_adelantos_eliminar(adv_id):
    db.session.delete(Advance.query.get_or_404(adv_id))
    db.session.commit()
    flash("Registro eliminado.", "info")
    return redirect(url_for("hr.hr_adelantos"))


# =====================================================================
# HISTORIAL DE PAGOS (sueldos registrados como gastos)
# =====================================================================

@hr_bp.route("/pagos")
@login_required
@role_required("administrador")
def hr_pagos():
    employee_id = request.args.get("employee_id", "").strip()
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()

    query = Expense.query.filter(Expense.category == "sueldos")
    if employee_id:
        query = query.filter(Expense.employee_id == int(employee_id))
    if desde:
        query = query.filter(Expense.expense_date >= _parse_date(desde))
    if hasta:
        query = query.filter(Expense.expense_date <= _parse_date(hasta))

    pagos = query.order_by(Expense.expense_date.desc(), Expense.expense_id.desc()).limit(300).all()
    total = sum(float(p.amount) for p in pagos)
    return render_template("hr_pagos.html", pagos=pagos, total=total, employees=_employees(),
                           selected_employee=employee_id, desde=desde, hasta=hasta)


# =====================================================================
# ASISTENCIA POR QR (pagina publica de marcado)
# =====================================================================

def _estado_hoy(employee_id):
    hoy = date.today()
    reg = (Attendance.query.filter_by(employee_id=employee_id, date=hoy)
           .order_by(Attendance.attendance_id.desc()).first())
    if reg and reg.check_in and not reg.check_out:
        return "dentro"
    if reg and reg.check_in and reg.check_out:
        return "fuera"
    return "sin"


@hr_bp.route("/checkin")
def hr_checkin():
    """Pagina publica (se abre al escanear el QR). El empleado marca entrada/salida."""
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()
    preselect = request.args.get("emp", "")
    estados = {e.employee_id: _estado_hoy(e.employee_id) for e in employees}
    return render_template("hr_checkin.html", employees=employees, estados=estados, preselect=preselect)


@hr_bp.route("/checkin/marcar", methods=["POST"])
def hr_checkin_marcar():
    emp = Employee.query.get(request.form.get("employee_id")) if request.form.get("employee_id") else None
    accion = request.form.get("accion", "entrada")
    if not emp or not emp.active:
        flash("Empleado no válido.", "danger")
        return redirect(url_for("hr.hr_checkin"))

    hoy = date.today()
    ahora = datetime.now().time().replace(microsecond=0)
    reg = (Attendance.query.filter_by(employee_id=emp.employee_id, date=hoy)
           .order_by(Attendance.attendance_id.desc()).first())

    if accion == "entrada":
        if reg and reg.check_in and not reg.check_out:
            flash(f"{emp.name} ya tiene una entrada abierta hoy.", "warning")
        else:
            db.session.add(Attendance(employee_id=emp.employee_id, date=hoy, check_in=ahora))
            db.session.commit()
            flash(f"✅ Entrada registrada: {emp.name} a las {ahora.strftime('%H:%M')}.", "success")
    else:  # salida
        if not reg or not reg.check_in:
            flash(f"No hay entrada registrada hoy para {emp.name}.", "warning")
        elif reg.check_out:
            flash(f"{emp.name} ya registró su salida hoy.", "warning")
        else:
            reg.check_out = ahora
            db.session.commit()
            flash(f"🏁 Salida registrada: {emp.name} a las {ahora.strftime('%H:%M')}.", "success")

    return redirect(url_for("hr.hr_checkin", emp=emp.employee_id))


@hr_bp.route("/qr")
@login_required
@role_required("administrador")
def hr_qr():
    """Muestra el QR para imprimir y ponerlo en la entrada."""
    base = request.url_root.rstrip("/")
    checkin_url = base + url_for("hr.hr_checkin")
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()
    emp_urls = [(e, base + url_for("hr.hr_checkin") + "?emp=" + str(e.employee_id)) for e in employees]
    return render_template("hr_qr.html", checkin_url=checkin_url, emp_urls=emp_urls)

