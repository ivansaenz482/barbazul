"""
Migracion: cajas por punto (usuario).
- Crea la tabla caja_dias.
- Agrega la columna expenses.caja_user_id.

Uso (base real):  python migrar_cajas.py
Demo:             set DB_NAME=sistema_inventario_huang_demo && python migrar_cajas.py
Nube (Railway):   set DATABASE_URL=... && python migrar_cajas.py
"""
from sqlalchemy import text
from app import create_app
from app.extensions import db

app = create_app()


def _columnas(tabla):
    return [r[0] for r in db.session.execute(text(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
    ), {"t": tabla}).fetchall()]


if __name__ == "__main__":
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])
        db.create_all()
        print("Tabla caja_dias lista.")
        if db.engine.dialect.name == "mysql":
            if "caja_user_id" not in _columnas("expenses"):
                db.session.execute(text("ALTER TABLE expenses ADD COLUMN caja_user_id INT NULL"))
                db.session.commit()
                print("Columna expenses.caja_user_id agregada.")
            else:
                print("Columna expenses.caja_user_id ya existe.")
