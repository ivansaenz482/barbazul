"""
Migracion: stock por sucursal (completo).

- Crea la tabla branch_stock (stock por sucursal).
- Convierte las columnas de ubicacion de ENUM('local','matriz') a VARCHAR(30),
  para poder guardar "sucursal:<id>".
- Agrega purchase_invoices.bodega_destino.

Uso (base real):  python migrar_sucursales.py
Demo:             set DB_NAME=sistema_inventario_huang_demo && python migrar_sucursales.py
Nube (Railway):   set DATABASE_URL=mysql+pymysql://root:<pass>@<proxy_host>:<port>/railway && python migrar_sucursales.py
"""
from sqlalchemy import text
from app import create_app
from app.extensions import db

app = create_app()

MODIFICAR = [
    "ALTER TABLE users MODIFY COLUMN bodega VARCHAR(30) NULL",
    "ALTER TABLE sales MODIFY COLUMN bodega VARCHAR(30) NULL",
    "ALTER TABLE sales_goals MODIFY COLUMN bodega VARCHAR(30) NULL",
    "ALTER TABLE notas_credito MODIFY COLUMN bodega VARCHAR(30) NULL",
    "ALTER TABLE supplier_orders MODIFY COLUMN bodega_destino VARCHAR(30) NULL",
]

AGREGAR = [
    ("purchase_invoices", "bodega_destino", "ALTER TABLE purchase_invoices ADD COLUMN bodega_destino VARCHAR(30) NULL"),
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
        print("Tabla branch_stock lista.")

        if db.engine.dialect.name != "mysql":
            print("Motor no MySQL: ajustes de columnas omitidos.")
        else:
            for sql in MODIFICAR:
                try:
                    db.session.execute(text(sql))
                except Exception as e:
                    print("Aviso:", e)
            for tabla, col, sql in AGREGAR:
                if col not in _columnas(tabla):
                    db.session.execute(text(sql))
            db.session.commit()
            print("Columnas de ubicacion actualizadas (VARCHAR + bodega_destino).")
