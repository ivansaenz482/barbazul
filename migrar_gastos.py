"""
Migracion para GASTOS y PERSONAL: crea las tablas employees y expenses.
Uso (base real): python migrar_gastos.py
Demo: set DB_NAME=sistema_inventario_huang_demo && python migrar_gastos.py
"""
from app import create_app
from app.extensions import db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])
        db.create_all()
        print("Tablas employees y expenses listas.")
