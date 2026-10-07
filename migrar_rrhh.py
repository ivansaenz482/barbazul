"""
Migracion para RECURSOS HUMANOS: crea las tablas attendance, leave_requests y advances.
Uso (base real): python migrar_rrhh.py
Demo: set DB_NAME=sistema_inventario_huang_demo && python migrar_rrhh.py
"""
from app import create_app
from app.extensions import db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])
        db.create_all()
        print("Tablas de RRHH listas (attendance, leave_requests, advances).")
