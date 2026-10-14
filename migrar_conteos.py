"""
Migracion: inventario fisico con conteo.
Crea las tablas conteos_inventario y conteo_detalles.
Uso: python migrar_conteos.py  (o con DATABASE_URL para la nube)
"""
from app import create_app
from app.extensions import db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])
        db.create_all()
        print("Tablas conteos_inventario / conteo_detalles listas.")
