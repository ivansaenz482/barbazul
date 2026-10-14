"""
Migracion: mejoras varias (lunch, mecanico, rol mecanico).

- attendance.lunch_out, attendance.lunch_in
- sales.mecanico_id
- employees.role incluye 'mecanico'

Uso (base real):  python migrar_mejoras.py
Demo:             set DB_NAME=sistema_inventario_huang_demo && python migrar_mejoras.py
Nube (Railway):   set DATABASE_URL=... && python migrar_mejoras.py
"""
from sqlalchemy import text
from app import create_app
from app.extensions import db

app = create_app()

AGREGAR = [
    ("attendance", "lunch_out", "ALTER TABLE attendance ADD COLUMN lunch_out TIME NULL"),
    ("attendance", "lunch_in", "ALTER TABLE attendance ADD COLUMN lunch_in TIME NULL"),
    ("sales", "mecanico_id", "ALTER TABLE sales ADD COLUMN mecanico_id INT NULL"),
]

ENUM_ROLE = ("ALTER TABLE employees MODIFY COLUMN role "
             "ENUM('vendedor','chofer','administrador','bodeguero','mecanico','otro') "
             "NOT NULL DEFAULT 'vendedor'")


def _columnas(tabla):
    return [r[0] for r in db.session.execute(text(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
    ), {"t": tabla}).fetchall()]


if __name__ == "__main__":
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])
        db.create_all()
        if db.engine.dialect.name != "mysql":
            print("Motor no MySQL: omitido.")
        else:
            for tabla, col, sql in AGREGAR:
                if col not in _columnas(tabla):
                    db.session.execute(text(sql))
                    print(f"Columna {tabla}.{col} agregada.")
                else:
                    print(f"Columna {tabla}.{col} ya existe.")
            try:
                db.session.execute(text(ENUM_ROLE))
                print("Enum employees.role actualizado (incluye 'mecanico').")
            except Exception as e:
                print("Aviso enum:", e)
            db.session.commit()
            print("Listo.")
