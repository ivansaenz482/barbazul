"""
Envia por correo los RECORDATORIOS del sistema:
  - Vencimientos de impuestos (SRI)
  - Bajo / sobre stock
  - Creditos de clientes vencidos y por vencer
  - Pagos a proveedores vencidos y proximos

Requiere configurar SMTP_* en el archivo .env (igual que las alertas).
Si no hay nada pendiente, no envia nada.

Uso manual:
    python send_reminders.py

Automatico: programa este archivo con el Programador de Tareas de Windows
(ej. todos los dias a las 8:00 AM) para recibir los recordatorios.
"""
from app import create_app
from app.notifications import send_reminders_email

app = create_app()

with app.app_context():
    ok, mensaje = send_reminders_email()
    print(mensaje)
