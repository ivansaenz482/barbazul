"""
Migracion: agrega company_settings.system_name (nombre del sistema configurable).
Uso (base real): python migrar_nombre_sistema.py
Demo: set DB_NAME=sistema_inventario_huang_demo && python migrar_nombre_sistema.py
"""
from sqlalchemy import text

from app import create_app
from app.extensions import db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        dbn = app.config["DB_NAME"]
        print("Base: " + dbn)
        with db.engine.connect() as conn:
            existe = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema=:db AND table_name='company_settings' AND column_name='system_name'"
            ).bindparams(db=dbn)).scalar()
            if not existe:
                conn.execute(text("ALTER TABLE company_settings ADD COLUMN system_name VARCHAR(120) NULL"))
                conn.commit()
                print("  + company_settings.system_name")
            else:
                print("  = company_settings.system_name ya existe")
        print("Migracion completada.")
