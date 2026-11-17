"""
Caja por punto (usuario): el administrador asigna el fondo (apertura) de cada
caja, registra el cierre del dia, y el valor del cierre arranca la caja del
dia siguiente. Los gastos se pueden cargar a la caja de un usuario.

Incluye arqueo por denominaciones (billetes y monedas) y un acta de cierre
lista para imprimir y firmar.
"""
import json
from datetime import datetime, date, time

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import User, Payment, Sale, Expense, CajaDia, CompanySetting
from app.utils import role_required
from app.audit import registrar

cajas_bp = Blueprint("cajas", __name__, url_prefix="/cajas")

# Denominaciones del dolar (Ecuador). (clave, valor, etiqueta, tipo)
DENOMINACIONES = [
    ("100", 100.00, "Billete de $100", "billete"),
    ("50", 50.00, "Billete de $50", "billete"),
    ("20", 20.00, "Billete de $20", "billete"),
    ("10", 10.00, "Billete de $10", "billete"),
    ("5", 5.00, "Billete de $5", "billete"),
    ("2", 2.00, "Moneda de $2", "moneda"),
    ("1", 1.00, "Moneda de $1", "moneda"),
    ("050", 0.50, "Moneda de 50 centavos", "moneda"),
    ("025", 0.25, "Moneda de 25 centavos", "moneda"),
    ("010", 0.10, "Moneda de 10 centavos", "moneda"),
    ("005", 0.05, "Moneda de 5 centavos", "moneda"),
    ("001", 0.01, "Moneda de 1 centavo", "moneda"),
]


def _rango(fecha):
    return datetime.combine(fecha, time.min), datetime.combine(fecha, time.max)


def _num(valor):
    try:
        return round(float(str(valor).replace("$", "").replace(",", "").strip() or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _fecha_arg(valor):
    try:
        return datetime.strptime((valor or "").strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _pagos_efectivo(user_id, fecha):
    ini, fin = _rango(fecha)
    return (Payment.query.join(Sale)
            .filter(Sale.user_id == user_id, Payment.payment_date >= ini, Payment.payment_date <= fin,
                    Payment.payment_method == "efectivo")
            .order_by(Payment.payment_date.asc(), Payment.payment_id.asc()).all())


def _cobros_efectivo(user_id, fecha):
    return round(sum(float(p.amount or 0) for p in _pagos_efectivo(user_id, fecha)), 2)


def _cobros_por_metodo(user_id, fecha):
    """Totales cobrados por metodo de pago (efectivo, tarjeta, transferencia...)."""
    ini, fin = _rango(fecha)
    pagos = (Payment.query.join(Sale)
             .filter(Sale.user_id == user_id, Payment.payment_date >= ini, Payment.payment_date <= fin)
             .all())
    totales = {}
    for p in pagos:
        metodo = p.payment_method or "otro"
        totales[metodo] = round(totales.get(metodo, 0.0) + float(p.amount or 0), 2)
    return totales


def _gastos_caja(user_id, fecha):
    gs = (Expense.query
          .filter(Expense.caja_user_id == user_id, Expense.expense_date == fecha)
          .order_by(Expense.expense_id.desc()).all())
    return round(sum(float(g.amount or 0) for g in gs), 2), gs


def _caja_de(user_id, fecha):
    return CajaDia.query.filter_by(user_id=user_id, fecha=fecha).first()


def _apertura_sugerida(user_id, fecha):
    prev = (CajaDia.query
            .filter(CajaDia.user_id == user_id, CajaDia.fecha < fecha, CajaDia.monto_cierre.isnot(None))
            .order_by(CajaDia.fecha.desc()).first())
    return float(prev.monto_cierre) if prev and prev.monto_cierre is not None else 0.0


def _cargar_arqueo(caja):
    """Devuelve el dict {clave_denominacion: cantidad} guardado en la caja."""
    if not caja or not caja.detalle_arqueo:
        return {}
    try:
        data = json.loads(caja.detalle_arqueo)
    except (TypeError, ValueError):
        return {}
    detalle = {}
    for clave, cantidad in (data or {}).items():
        try:
            cantidad = int(cantidad)
        except (TypeError, ValueError):
            continue
        if cantidad > 0:
            detalle[str(clave)] = cantidad
    return detalle


def _lineas_arqueo(detalle):
    """Convierte el detalle en lineas legibles con subtotales y total."""
    lineas = []
    total = 0.0
    for clave, valor, etiqueta, tipo in DENOMINACIONES:
        cantidad = int((detalle or {}).get(clave, 0) or 0)
        if cantidad <= 0:
            continue
        subtotal = round(cantidad * valor, 2)
        total = round(total + subtotal, 2)
        lineas.append({
            "clave": clave, "valor": valor, "etiqueta": etiqueta,
            "tipo": tipo, "cantidad": cantidad, "subtotal": subtotal,
        })
    return lineas, total


def _leer_arqueo(form):
    """Lee los campos denom_* del formulario y devuelve (detalle, total)."""
    detalle = {}
    total = 0.0
    for clave, valor, _etiqueta, _tipo in DENOMINACIONES:
        raw = (form.get(f"denom_{clave}") or "").strip()
        try:
            cantidad = int(raw) if raw else 0
        except ValueError:
            cantidad = 0
        if cantidad > 0:
            detalle[clave] = cantidad
            total = round(total + cantidad * valor, 2)
    return detalle, total


def _resumen_dia(user_id, fecha, apertura):
    cobros = _cobros_efectivo(user_id, fecha)
    gastos, lista_gastos = _gastos_caja(user_id, fecha)
    esperado = round(apertura + cobros - gastos, 2)
    return cobros, gastos, lista_gastos, esperado


@cajas_bp.route("/")
@login_required
@role_required("administrador")
def cajas_list():
    fecha = _fecha_arg(request.args.get("fecha")) or date.today()

    usuarios = User.query.filter(User.active.is_(True)).order_by(User.full_name).all()
    filas = []
    tot_apertura = tot_cobros = tot_gastos = tot_esperado = tot_cierre = tot_diferencia = 0.0
    cerradas = pendientes = 0

    for u in usuarios:
        caja = _caja_de(u.user_id, fecha)
        apertura = float(caja.monto_apertura) if caja else _apertura_sugerida(u.user_id, fecha)
        cierre = float(caja.monto_cierre) if (caja and caja.monto_cierre is not None) else None
        cobros, gastos, lista_gastos, esperado = _resumen_dia(u.user_id, fecha, apertura)
        diferencia = round(cierre - esperado, 2) if cierre is not None else None
        filas.append({
            "user": u,
            "punto": (caja.punto if caja else ""),
            "apertura": apertura,
            "cobros": cobros,
            "gastos": gastos,
            "gastos_lista": lista_gastos,
            "esperado": esperado,
            "cierre": cierre,
            "diferencia": diferencia,
            "notas": (caja.notas if caja else ""),
            "arqueo": _cargar_arqueo(caja),
            "cerrada": cierre is not None,
            "cerrado_at": (caja.cerrado_at if caja else None),
        })
        tot_apertura += apertura
        tot_cobros += cobros
        tot_gastos += gastos
        tot_esperado += esperado
        if cierre is not None:
            cerradas += 1
            tot_cierre += cierre
            tot_diferencia += diferencia
        else:
            pendientes += 1

    return render_template(
        "cajas_list.html", filas=filas, fecha=fecha.strftime("%Y-%m-%d"),
        denominaciones=DENOMINACIONES,
        tot_apertura=round(tot_apertura, 2), tot_cobros=round(tot_cobros, 2),
        tot_gastos=round(tot_gastos, 2), tot_esperado=round(tot_esperado, 2),
        tot_cierre=round(tot_cierre, 2), tot_diferencia=round(tot_diferencia, 2),
        cerradas=cerradas, pendientes=pendientes,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


@cajas_bp.route("/guardar", methods=["POST"])
@login_required
@role_required("administrador")
def caja_guardar():
    try:
        user_id = int(request.form.get("user_id"))
    except (TypeError, ValueError):
        user_id = None
    fecha = _fecha_arg(request.form.get("fecha"))

    if not user_id or not fecha:
        flash("Datos de caja inválidos.", "danger")
        return redirect(url_for("cajas.cajas_list"))

    if not User.query.get(user_id):
        flash("El usuario de la caja no existe.", "danger")
        return redirect(url_for("cajas.cajas_list", fecha=fecha.strftime("%Y-%m-%d")))

    caja = _caja_de(user_id, fecha)
    if not caja:
        caja = CajaDia(user_id=user_id, fecha=fecha)
        db.session.add(caja)

    apertura = _num(request.form.get("monto_apertura"))
    punto = (request.form.get("punto") or "").strip()
    notas = (request.form.get("notas") or "").strip() or None

    detalle, total_arqueo = _leer_arqueo(request.form)
    cierre_txt = (request.form.get("monto_cierre") or "").strip()

    # Si se contaron denominaciones, mandan ellas; si no, el valor manual.
    if detalle:
        monto_cierre = total_arqueo
    elif cierre_txt:
        monto_cierre = _num(cierre_txt)
    else:
        monto_cierre = None

    # Guardar con diferencia sin justificar no es un cierre confiable.
    if monto_cierre is not None:
        _cobros, _gastos, _lista, esperado = _resumen_dia(user_id, fecha, apertura)
        diferencia = round(monto_cierre - esperado, 2)
        if abs(diferencia) > 0.009 and not notas:
            flash(
                f"El cierre de {User.query.get(user_id).full_name} tiene una diferencia de "
                f"${diferencia:,.2f}. Escribe una nota justificando la diferencia para guardarlo.",
                "danger",
            )
            return redirect(url_for("cajas.cajas_list", fecha=fecha.strftime("%Y-%m-%d")))

    caja.monto_apertura = apertura
    caja.monto_cierre = monto_cierre
    caja.detalle_arqueo = json.dumps(detalle, ensure_ascii=False) if (detalle and monto_cierre is not None) else None
    caja.punto = punto or caja.punto
    caja.notas = notas
    caja.registrado_por = current_user.user_id

    if monto_cierre is not None:
        if caja.cerrado_at is None:
            caja.cerrado_at = datetime.now()
            caja.cerrado_por = current_user.user_id
    else:
        # Al borrar el cierre, la caja vuelve a quedar abierta.
        caja.cerrado_at = None
        caja.cerrado_por = None

    db.session.commit()
    registrar(
        "caja_actualizada",
        detalle=f"Caja de usuario #{user_id} actualizada ({fecha.strftime('%d/%m/%Y')})"
                + (f" · cierre ${monto_cierre:,.2f}" if monto_cierre is not None else " · abierta"),
        entidad="caja",
    )
    if monto_cierre is not None:
        flash("Caja cerrada y arqueo guardado correctamente.", "success")
    else:
        flash("Caja actualizada (abierta).", "success")
    return redirect(url_for("cajas.cajas_list", fecha=fecha.strftime("%Y-%m-%d")))


@cajas_bp.route("/mi-caja")
@login_required
def mi_caja():
    fecha = date.today()
    caja = _caja_de(current_user.user_id, fecha)
    apertura = float(caja.monto_apertura) if caja else _apertura_sugerida(current_user.user_id, fecha)
    cobros, gastos, lista_gastos, esperado = _resumen_dia(current_user.user_id, fecha, apertura)
    cierre = float(caja.monto_cierre) if (caja and caja.monto_cierre is not None) else None
    diferencia = round(cierre - esperado, 2) if cierre is not None else None
    detalle = _cargar_arqueo(caja)
    lineas, total_arqueo = _lineas_arqueo(detalle)

    return render_template(
        "mi_caja.html", fecha=fecha, apertura=apertura, cobros=cobros,
        gastos=gastos, gastos_lista=lista_gastos, esperado=esperado, caja=caja,
        cierre=cierre, diferencia=diferencia, lineas_arqueo=lineas,
        total_arqueo=total_arqueo, denominaciones=DENOMINACIONES,
        pagos=_pagos_efectivo(current_user.user_id, fecha),
        por_metodo=_cobros_por_metodo(current_user.user_id, fecha),
    )


@cajas_bp.route("/cierre/<int:user_id>/<fecha>")
@login_required
def caja_cierre_acta(user_id, fecha):
    """Acta de cierre imprimible. El admin ve cualquiera; el cajero solo la suya."""
    dia = _fecha_arg(fecha)
    if not dia:
        abort(404)
    if not current_user.is_admin() and current_user.user_id != user_id:
        abort(403)

    user = User.query.get_or_404(user_id)
    caja = _caja_de(user_id, dia)
    if not caja or caja.monto_cierre is None:
        flash("Esa caja todavía no está cerrada.", "warning")
        return redirect(url_for("cajas.mi_caja") if user_id == current_user.user_id else url_for("cajas.cajas_list"))

    apertura = float(caja.monto_apertura or 0)
    cobros, gastos, lista_gastos, esperado = _resumen_dia(user_id, dia, apertura)
    cierre = float(caja.monto_cierre)
    detalle = _cargar_arqueo(caja)
    lineas, total_arqueo = _lineas_arqueo(detalle)

    return render_template(
        "caja_cierre_acta.html", user=user, caja=caja, fecha=dia,
        apertura=apertura, cobros=cobros, gastos=gastos, gastos_lista=lista_gastos,
        esperado=esperado, cierre=cierre, diferencia=round(cierre - esperado, 2),
        lineas_arqueo=lineas, total_arqueo=total_arqueo,
        pagos=_pagos_efectivo(user_id, dia), por_metodo=_cobros_por_metodo(user_id, dia),
        company=CompanySetting.actual(),
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
