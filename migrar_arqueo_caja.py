"""
Migracion: arqueo de caja por denominaciones y acta de cierre.

Agrega a la tabla caja_dias:
  - detalle_arqueo  TEXT     (JSON con el conteo de billetes/monedas)
  - cerrado_por     INT      (usuario que cerro la caja)
  - cerrado_at      DATETIME (fecha y hora del cierre)

Uso (base real):  python migrar_arqueo_caja.py
Demo:             set DB_NAME=sistema_inventario_huang_demo && python migrar_arqueo_caja.py
Nube (Railway):   set DATABASE_URL=... && python migrar_arqueo_caja.py
"""
from sqlalchemy import text

from app import create_app
from app.extensions import db

app = create_app()

COLUMNAS = {
    "detalle_arqueo": "TEXT NULL",
    "cerrado_por": "INT NULL",
    "cerrado_at": "DATETIME NULL",
}


def _columnas_mysql(tabla):
    return [r[0] for r in db.session.execute(text(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
    ), {"t": tabla}).fetchall()]


def _columnas_sqlite(tabla):
    return [r[1] for r in db.session.execute(text(f"PRAGMA table_info({tabla})")).fetchall()]


if __name__ == "__main__":
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])

        # En una base nueva, create_all ya crea la tabla con las columnas.
        db.create_all()
        print("Tabla caja_dias verificada.")

        dialecto = db.engine.dialect.name
        if dialecto == "mysql":
            existentes = _columnas_mysql("caja_dias")
            for columna, definicion in COLUMNAS.items():
                if columna not in existentes:
                    db.session.execute(text(f"ALTER TABLE caja_dias ADD COLUMN {columna} {definicion}"))
                    db.session.commit()
                    print(f"Columna caja_dias.{columna} agregada.")
                else:
                    print(f"Columna caja_dias.{columna} ya existe.")
        elif dialecto == "sqlite":
            existentes = _columnas_sqlite("caja_dias")
            for columna, definicion in COLUMNAS.items():
                if columna not in existentes:
                    db.session.execute(text(f"ALTER TABLE caja_dias ADD COLUMN {columna} {definicion}"))
                    db.session.commit()
                    print(f"Columna caja_dias.{columna} agregada.")
                else:
                    print(f"Columna caja_dias.{columna} ya existe.")
        else:
            print(f"Dialecto '{dialecto}': revisa manualmente las columnas {', '.join(COLUMNAS)}.")

        print("\nListo. La caja ya soporta arqueo por denominaciones y acta de cierre.")
