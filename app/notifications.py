"""
Envio del correo-resumen de alertas.

No requiere ninguna libreria nueva (usa smtplib, incluido en Python).
Se activa configurando las variables SMTP_* en el archivo .env:

    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=tucorreo@gmail.com
    SMTP_PASSWORD=una_clave_de_aplicacion_de_gmail   <- NO tu contraseña normal
    ALERT_EMAIL_TO=correo_donde_quieres_recibir_las_alertas@gmail.com

Si SMTP_HOST esta vacio, la funcion simplemente no hace nada (retorna False
con un mensaje explicando que no esta configurado), sin romper la aplicacion.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import current_app
from app.alerts_utils import (get_low_stock_products, get_overstock_products, get_overdue_credits,
                              get_upcoming_credits, get_upcoming_supplier_payments,
                              get_overdue_supplier_payments, get_tax_reminder)


def _build_message_body():
    bajo_stock = get_low_stock_products()
    sobre_stock = get_overstock_products()
    vencidos = get_overdue_credits()

    if not bajo_stock and not sobre_stock and not vencidos:
        return None  # no hay nada que avisar

    lineas = ["Resumen de alertas del Sistema de Inventario", "=" * 45, ""]

    if bajo_stock:
        lineas.append(f"⚠ BAJO STOCK ({len(bajo_stock)} productos):")
        for p in bajo_stock:
            lineas.append(f"  - {p.name}: {p.current_stock} unidades (mínimo: {p.min_stock})")
        lineas.append("")

    if sobre_stock:
        lineas.append(f"📈 SOBRE STOCK ({len(sobre_stock)} productos):")
        for p in sobre_stock:
            lineas.append(f"  - {p.name}: {p.current_stock} unidades (máximo: {p.max_stock})")
        lineas.append("")

    if vencidos:
        lineas.append(f"🚨 CRÉDITOS VENCIDOS ({len(vencidos)} ventas):")
        for s in vencidos:
            lineas.append(f"  - Venta #{s.sale_id} — {s.customer.full_name}: ${s.saldo_pendiente():.2f} (venció {s.due_date.strftime('%d/%m/%Y')})")
        lineas.append("")

    return "\n".join(lineas)


def send_alert_email():
    """
    Envia el correo de alertas si hay algo pendiente.
    Devuelve una tupla (exito: bool, mensaje: str) para mostrar al usuario o al log.
    """
    smtp_host = current_app.config.get("SMTP_HOST", "").strip()
    smtp_port = current_app.config.get("SMTP_PORT", "587")
    smtp_user = current_app.config.get("SMTP_USER", "").strip()
    smtp_password = current_app.config.get("SMTP_PASSWORD", "").strip()
    email_to = current_app.config.get("ALERT_EMAIL_TO", "").strip()

    if not smtp_host or not smtp_user or not smtp_password or not email_to:
        return False, (
            "El envío de correo no está configurado. "
            "Completa las variables SMTP_* en tu archivo .env para activarlo."
        )

    cuerpo = _build_message_body()
    if cuerpo is None:
        return True, "No hay alertas pendientes en este momento. No se envió ningún correo."

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = email_to
    msg["Subject"] = "Alertas del Sistema de Inventario"
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True, f"Correo de alertas enviado correctamente a {email_to}."
    except Exception as e:
        return False, f"No se pudo enviar el correo: {e}"


def _smtp_configurado():
    return all([
        current_app.config.get("SMTP_HOST", "").strip(),
        current_app.config.get("SMTP_USER", "").strip(),
        current_app.config.get("SMTP_PASSWORD", "").strip(),
        current_app.config.get("ALERT_EMAIL_TO", "").strip(),
    ])


def _enviar(destino, asunto, cuerpo):
    """Envia un correo de texto simple. Devuelve (ok, mensaje)."""
    smtp_host = current_app.config.get("SMTP_HOST", "").strip()
    smtp_port = current_app.config.get("SMTP_PORT", "587")
    smtp_user = current_app.config.get("SMTP_USER", "").strip()
    smtp_password = current_app.config.get("SMTP_PASSWORD", "").strip()
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = destino
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))
    try:
        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True, f"Correo enviado correctamente a {destino}."
    except Exception as e:
        return False, f"No se pudo enviar el correo: {e}"


def build_reminders_body():
    """Arma el cuerpo de texto con todos los recordatorios. Devuelve str o None."""
    from datetime import datetime as _dt
    lineas = [f"RECORDATORIOS — {_dt.now().strftime('%d/%m/%Y %H:%M')}", "=" * 48]
    hay = False

    tax = get_tax_reminder()
    if tax and tax["dias"] <= 10:
        hay = True
        lineas += ["", f"IMPUESTOS: declarar el IVA antes del {tax['fecha'].strftime('%d/%m/%Y')} "
                       f"(en {tax['dias']} día(s)). Ambiente: {tax.get('ambiente') or '—'}."]

    bajo = get_low_stock_products()
    if bajo:
        hay = True
        lineas += ["", f"BAJO STOCK ({len(bajo)} productos):"]
        for p in bajo[:20]:
            lineas.append(f"  - {p.name}: {p.total_stock()} (mínimo {p.min_stock})")

    sobre = get_overstock_products()
    if sobre:
        hay = True
        lineas += ["", f"SOBRE STOCK ({len(sobre)} productos):"]
        for p in sobre[:20]:
            lineas.append(f"  - {p.name}: {p.total_stock()} (máximo {p.max_stock})")

    vencidos = get_overdue_credits()
    if vencidos:
        hay = True
        lineas += ["", f"CRÉDITOS VENCIDOS ({len(vencidos)} ventas):"]
        for s in vencidos[:20]:
            lineas.append(f"  - Venta #{s.sale_id} — {s.customer.full_name}: ${s.saldo_pendiente():.2f} "
                          f"(venció {s.due_date.strftime('%d/%m/%Y')})")

    por_vencer = get_upcoming_credits(7)
    if por_vencer:
        hay = True
        lineas += ["", f"CRÉDITOS POR VENCER (próximos 7 días, {len(por_vencer)}):"]
        for s in por_vencer[:20]:
            lineas.append(f"  - Venta #{s.sale_id} — {s.customer.full_name}: ${s.saldo_pendiente():.2f} "
                          f"(vence {s.due_date.strftime('%d/%m/%Y')})")

    prov_vencidos = get_overdue_supplier_payments()
    if prov_vencidos:
        hay = True
        lineas += ["", f"PAGOS A PROVEEDORES VENCIDOS ({len(prov_vencidos)}):"]
        for inv in prov_vencidos[:20]:
            lineas.append(f"  - Compra #{inv.invoice_id} — {inv.supplier.name}: ${inv.saldo_pendiente():.2f} "
                          f"(venció {inv.due_date.strftime('%d/%m/%Y')})")

    prov_prox = get_upcoming_supplier_payments(15)
    if prov_prox:
        hay = True
        lineas += ["", f"PAGOS A PROVEEDORES PRÓXIMOS (15 días, {len(prov_prox)}):"]
        for inv in prov_prox[:20]:
            lineas.append(f"  - Compra #{inv.invoice_id} — {inv.supplier.name}: ${inv.saldo_pendiente():.2f} "
                          f"(vence {inv.due_date.strftime('%d/%m/%Y')})")

    if not hay:
        return None
    lineas += ["", "-" * 48, "Mensaje automático del Sistema de Facturación."]
    return "\n".join(lineas)


def send_reminders_email():
    """Envia el correo de recordatorios (impuestos, stock, créditos, pagos)."""
    cuerpo = build_reminders_body()
    if cuerpo is None:
        return True, "No hay recordatorios pendientes en este momento."

    # Notificacion push a los dispositivos suscritos (no depende del correo)
    try:
        from app.push_utils import enviar_push_a_todos
        enviar_push_a_todos("Recordatorios del Sistema",
                            "Tienes avisos pendientes (impuestos, stock, créditos).",
                            "/alertas/")
    except Exception:
        pass

    if not _smtp_configurado():
        return False, ("Notificaciones push enviadas. Para el correo, completa las variables SMTP_* en tu .env.")
    destino = current_app.config.get("ALERT_EMAIL_TO", "").strip()
    return _enviar(destino, "Recordatorios — Sistema de Facturación", cuerpo)
