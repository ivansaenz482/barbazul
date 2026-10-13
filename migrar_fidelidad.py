"""
Migracion: programa de fidelidad (puntos) + recordatorios.

- customers.points
- company_settings.puntos_por_dolar
- company_settings.valor_punto

Uso (base real):  python migrar_fidelidad.py
Demo:             set DB_NAME=sistema_inventario_huang_demo && python migrar_fidelidad.py
Nube (Railway):   set DATABASE_URL=... && python migrar_fidelidad.py
"""
from sqlalchemy import text
from app import create_app
from app.extensions import db

app = create_app()

AGREGAR = [
    ("customers", "points", "ALTER TABLE customers ADD COLUMN points INT NOT NULL DEFAULT 0"),
    ("company_settings", "puntos_por_dolar", "ALTER TABLE company_settings ADD COLUMN puntos_por_dolar INT NOT NULL DEFAULT 1"),
    ("company_settings", "valor_punto", "ALTER TABLE company_settings ADD COLUMN valor_punto DECIMAL(6,4) NOT NULL DEFAULT 0.01"),
]


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
            db.session.commit()
            print("Listo.")
