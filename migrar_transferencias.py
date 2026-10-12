"""
Migracion: modulo de transferencias entre bodegas.

- Crea las tablas stock_transfers y stock_transfer_details.
- Agrega el valor 'transferencia' al enum reference_type de inventory_movements (MySQL).

Uso (base real):  python migrar_transferencias.py
Demo:             set DB_NAME=sistema_inventario_huang_demo && python migrar_transferencias.py
Nube (Railway):   set DATABASE_URL=mysql+pymysql://root:<pass>@<proxy_host>:<port>/railway && python migrar_transferencias.py
"""
from sqlalchemy import text
from app import create_app
from app.extensions import db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])
        db.create_all()
        print("Tablas stock_transfers / stock_transfer_details listas.")

        if db.engine.dialect.name == "mysql":
            valores = "ENUM('compra','venta','ajuste_manual','pedido_proveedor','nota_credito','transferencia')"
            db.session.execute(text(
                f"ALTER TABLE inventory_movements MODIFY COLUMN reference_type {valores} NOT NULL"
            ))
            db.session.commit()
            print("Enum reference_type actualizado (incluye 'transferencia').")
        else:
            print("Motor no MySQL: no se ajusta el enum.")
