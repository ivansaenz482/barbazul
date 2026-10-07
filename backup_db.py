"""
Script independiente para generar un respaldo de la base de datos.

Uso manual:
    python backup_db.py

Uso automatico (recomendado): programa este script con el Programador de
Tareas de Windows para que corra todos los dias, por ejemplo a las 2:00 AM.
Instrucciones completas en README.md, seccion "Respaldo automático".
"""
from app import create_app
from app.backup_utils import create_backup

app = create_app()

with app.app_context():
    ok, mensaje, filepath = create_backup()
    print(mensaje)
