"""
Migracion para la seccion 'Pedidos a Proveedor':
  - Crea las tablas supplier_orders y supplier_order_details (si no existen).
  - Agrega el valor 'pedido_proveedor' al enum reference_type de inventory_movements.

Usa la base indicada en DB_NAME (por defecto la real). Para la demo:
    set DB_NAME=sistema_inventario_huang_demo && python migrar_pedidos_proveedor.py

Uso normal:
    python migrar_pedidos_proveedor.py
"""
from sqlalchemy import text

from app import create_app
from app.extensions import db

app = create_app()


def main():
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])
        print("[1] Creando tablas nuevas (si faltan)...")
        db.create_all()
        print("    OK.")

        print("[2] Actualizando enum inventory_movements.reference_type...")
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE inventory_movements "
                "MODIFY COLUMN reference_type "
                "ENUM('compra','venta','ajuste_manual','pedido_proveedor') NOT NULL"
            ))
            conn.commit()
        print("    OK.")
        print("Migracion completada.")


if __name__ == "__main__":
    main()
