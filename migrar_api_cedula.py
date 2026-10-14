"""
Migracion: API de consulta de cedula/RUC en company_settings.
Agrega: cedula_api_url, cedula_api_token, cedula_api_header.
Uso: python migrar_api_cedula.py  (o con DATABASE_URL para la nube)
"""
from sqlalchemy import text
from app import create_app
from app.extensions import db

app = create_app()

AGREGAR = [
    ("cedula_api_url", "ALTER TABLE company_settings ADD COLUMN cedula_api_url VARCHAR(300) NULL"),
    ("cedula_api_token", "ALTER TABLE company_settings ADD COLUMN cedula_api_token VARCHAR(300) NULL"),
    ("cedula_api_header", "ALTER TABLE company_settings ADD COLUMN cedula_api_header VARCHAR(60) NULL"),
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
        if db.engine.dialect.name == "mysql":
            cols = _columnas("company_settings")
            for col, sql in AGREGAR:
                if col not in cols:
                    db.session.execute(text(sql))
                    print(f"Columna company_settings.{col} agregada.")
                else:
                    print(f"Columna company_settings.{col} ya existe.")
            db.session.commit()
            print("Listo.")
