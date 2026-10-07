"""
Migracion NOTAS DE CREDITO:
  - Crea las tablas notas_credito y notas_credito_detalles.
  - Agrega el valor 'nota_credito' al enum reference_type de inventory_movements.
Uso (base real): python migrar_notas_credito.py
Demo: set DB_NAME=sistema_inventario_huang_demo && python migrar_notas_credito.py
"""
from sqlalchemy import text

from app import create_app
from app.extensions import db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        print("Base: " + app.config["DB_NAME"])
        db.create_all()
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE inventory_movements "
                "MODIFY COLUMN reference_type "
                "ENUM('compra','venta','ajuste_manual','pedido_proveedor','nota_credito') NOT NULL"
            ))
            conn.commit()
        print("Tablas de notas de crédito + enum actualizados.")
