from flask import Blueprint, render_template, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.alerts_utils import (get_low_stock_products, get_overstock_products, get_overdue_credits,
                              get_alerts_summary, get_upcoming_supplier_payments,
                              get_overdue_supplier_payments, get_upcoming_credits, get_tax_reminder)
from app.utils import role_required

alerts_bp = Blueprint("alerts", __name__, url_prefix="/alertas")


@alerts_bp.route("/")
@login_required
def alerts_page():
    bajo_stock = get_low_stock_products()
    sobre_stock = get_overstock_products()
    # Los creditos vencidos son informacion financiera: solo el administrador los ve aqui
    creditos_vencidos = get_overdue_credits() if current_user.is_admin() else []
    creditos_por_vencer = get_upcoming_credits(7) if current_user.is_admin() else []
    pagos_proximos = get_upcoming_supplier_payments() if current_user.is_admin() else []
    pagos_vencidos = get_overdue_supplier_payments() if current_user.is_admin() else []
    recordatorio_impuestos = get_tax_reminder() if current_user.is_admin() else None

    return render_template(
        "alerts_page.html",
        bajo_stock=bajo_stock,
        sobre_stock=sobre_stock,
        creditos_vencidos=creditos_vencidos,
        creditos_por_vencer=creditos_por_vencer,
        pagos_proximos=pagos_proximos,
        pagos_vencidos=pagos_vencidos,
        recordatorio_impuestos=recordatorio_impuestos,
    )


@alerts_bp.route("/resumen")
@login_required
def alerts_resumen():
    """Usado por la campanita de notificaciones en la barra superior (se consulta cada minuto)"""
    resumen = get_alerts_summary()
    if not current_user.is_admin():
        resumen["creditos_vencidos"] = 0  # el personal no ve alertas de creditos
        resumen["pagos_proveedores_proximos"] = 0
        resumen["pagos_proveedores_vencidos"] = 0
    resumen["total"] = resumen["bajo_stock"] + resumen["sobre_stock"] + resumen["creditos_vencidos"] + resumen["pagos_proveedores_proximos"] + resumen["pagos_proveedores_vencidos"]
    return jsonify(resumen)


@alerts_bp.route("/enviar-correo", methods=["POST"])
@login_required
@role_required("administrador")
def send_email_now():
    """Boton para probar el envio de correo de alertas manualmente"""
    from app.notifications import send_alert_email

    ok, mensaje = send_alert_email()
    flash(mensaje, "success" if ok else "danger")
    return redirect(url_for("alerts.alerts_page"))


@alerts_bp.route("/recordatorios/enviar", methods=["POST"])
@login_required
@role_required("administrador")
def send_reminders_now():
    """Envia el correo de recordatorios (impuestos, stock, créditos, pagos)."""
    from app.notifications import send_reminders_email

    ok, mensaje = send_reminders_email()
    flash(mensaje, "success" if ok else "danger")
    return redirect(url_for("alerts.alerts_page"))
