"""
Caja por punto (usuario): el administrador asigna el fondo (apertura) de cada
caja, registra el cierre del dia, y el valor del cierre arranca la caja del
dia siguiente. Los gastos se pueden cargar a la caja de un usuario.
"""
from datetime import datetime, date, time

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import User, Payment, Sale, Expense, CajaDia
from app.utils import role_required
from app.audit import registrar

cajas_bp = Blueprint("cajas", __name__, url_prefix="/cajas")


def _rango(fecha):
    return datetime.combine(fecha, time.min), datetime.combine(fecha, time.max)


def _num(valor):
    try:
        return round(float(str(valor).replace("$", "").replace(",", "").strip() or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _cobros_efectivo(user_id, fecha):
    ini, fin = _rango(fecha)
    pagos = (Payment.query.join(Sale)
             .filter(Sale.user_id == user_id, Payment.payment_date >= ini, Payment.payment_date <= fin,
                     Payment.payment_method == "efectivo").all())
    return sum(float(p.amount or 0) for p in pagos)


def _gastos_caja(user_id, fecha):
    gs = (Expense.query
          .filter(Expense.caja_user_id == user_id, Expense.expense_date == fecha)
          .order_by(Expense.expense_id.desc()).all())
    return sum(float(g.amount or 0) for g in gs), gs


def _caja_de(user_id, fecha):
    return CajaDia.query.filter_by(user_id=user_id, fecha=fecha).first()


def _apertura_sugerida(user_id, fecha):
    prev = (CajaDia.query
            .filter(CajaDia.user_id == user_id, CajaDia.fecha < fecha, CajaDia.monto_cierre.isnot(None))
            .order_by(CajaDia.fecha.desc()).first())
    return float(prev.monto_cierre) if prev and prev.monto_cierre is not None else 0.0


@cajas_bp.route("/")
@login_required
@role_required("administrador")
def cajas_list():
    fecha_str = request.args.get("fecha", "").strip()
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else date.today()
    except ValueError:
        fecha = date.today()

    usuarios = User.query.filter(User.active.is_(True)).order_by(User.full_name).all()
    filas = []
    tot_esperado = tot_cierre = 0.0
    for u in usuarios:
        caja = _caja_de(u.user_id, fecha)
        apertura = float(caja.monto_apertura) if caja else _apertura_sugerida(u.user_id, fecha)
        cierre = float(caja.monto_cierre) if (caja and caja.monto_cierre is not None) else None
        cobros = _cobros_efectivo(u.user_id, fecha)
        gastos, lista_gastos = _gastos_caja(u.user_id, fecha)
        esperado = round(apertura + cobros - gastos, 2)
        diferencia = round(cierre - esperado, 2) if cierre is not None else None
        filas.append({
            "user": u, "punto": (caja.punto if caja else ""), "apertura": apertura,
            "cobros": cobros, "gastos": gastos, "gastos_lista": lista_gastos,
            "esperado": esperado, "cierre": cierre, "diferencia": diferencia,
            "notas": (caja.notas if caja else ""),
        })
        tot_esperado += esperado
        if cierre is not None:
            tot_cierre += cierre

    return render_template("cajas_list.html", filas=filas, fecha=fecha.strftime("%Y-%m-%d"),
                           tot_esperado=tot_esperado, tot_cierre=tot_cierre,
                           generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"))


@cajas_bp.route("/guardar", methods=["POST"])
@login_required
@role_required("administrador")
def caja_guardar():
    try:
        user_id = int(request.form.get("user_id"))
        fecha = datetime.strptime(request.form.get("fecha"), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        flash("Datos de caja inválidos.", "danger")
        return redirect(url_for("cajas.cajas_list"))

    caja = _caja_de(user_id, fecha)
    if not caja:
        caja = CajaDia(user_id=user_id, fecha=fecha)
        db.session.add(caja)

    caja.monto_apertura = _num(request.form.get("monto_apertura"))
    cierre_txt = (request.form.get("monto_cierre") or "").strip()
    caja.monto_cierre = _num(cierre_txt) if cierre_txt else None
    caja.punto = (request.form.get("punto") or "").strip() or caja.punto
    caja.notas = (request.form.get("notas") or "").strip() or None
    caja.registrado_por = current_user.user_id
    db.session.commit()
    registrar("caja_actualizada", detalle=f"Caja de usuario #{user_id} actualizada ({fecha.strftime('%d/%m/%Y')})", entidad="caja")
    flash("Caja actualizada correctamente.", "success")
    return redirect(url_for("cajas.cajas_list", fecha=fecha.strftime("%Y-%m-%d")))


@cajas_bp.route("/mi-caja")
@login_required
def mi_caja():
    fecha = date.today()
    caja = _caja_de(current_user.user_id, fecha)
    apertura = float(caja.monto_apertura) if caja else _apertura_sugerida(current_user.user_id, fecha)
    cobros = _cobros_efectivo(current_user.user_id, fecha)
    gastos, lista_gastos = _gastos_caja(current_user.user_id, fecha)
    esperado = round(apertura + cobros - gastos, 2)
    return render_template("mi_caja.html", fecha=fecha, apertura=apertura, cobros=cobros,
                           gastos=gastos, gastos_lista=lista_gastos, esperado=esperado,
                           caja=caja)
