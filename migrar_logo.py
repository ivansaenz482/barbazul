"""
Migracion: crea la tabla company_settings (logo del negocio).
Uso (base real): python migrar_logo.py
Demo: set DB_NAME=sistema_inventario_huang_demo && python migrar_logo.py
"""
from app import create_app
from app.extensions import db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])
        db.create_all()
        print("Tabla company_settings lista.")
