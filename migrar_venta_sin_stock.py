"""
Migracion: agrega la columna company_settings.permitir_venta_sin_stock.

Uso (base real):  python migrar_venta_sin_stock.py
Demo:             set DB_NAME=sistema_inventario_huang_demo && python migrar_venta_sin_stock.py
Nube (Railway):   set DATABASE_URL=mysql+pymysql://root:<pass>@<proxy_host>:<port>/railway && python migrar_venta_sin_stock.py
"""
from sqlalchemy import text
from app import create_app
from app.extensions import db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])
        db.create_all()
        cols = [r[0] for r in db.session.execute(text(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'company_settings'"
        )).fetchall()]
        if "permitir_venta_sin_stock" not in cols:
            db.session.execute(text(
                "ALTER TABLE company_settings ADD COLUMN permitir_venta_sin_stock TINYINT(1) NOT NULL DEFAULT 0"
            ))
            db.session.commit()
            print("Columna 'permitir_venta_sin_stock' agregada.")
        else:
            print("La columna ya existe. Nada que hacer.")
