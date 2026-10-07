"""
Script independiente para revisar alertas y enviar el correo-resumen.

Uso manual:
    python send_alerts.py

Uso automatico (recomendado): programa este script con el Programador de
Tareas de Windows para que corra, por ejemplo, todos los dias a las 8:00 AM.
Instrucciones completas en README.md, seccion "Notificaciones automaticas".
"""
from app import create_app
from app.notifications import send_alert_email

app = create_app()

with app.app_context():
    ok, mensaje = send_alert_email()
    print(mensaje)
