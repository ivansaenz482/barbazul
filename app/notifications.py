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
from app.alerts_utils import get_low_stock_products, get_overstock_products, get_overdue_credits


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
