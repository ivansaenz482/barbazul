"""
Migracion para VENDEDORES:
  - Crea la tabla sellers.
  - Agrega la columna sales.vendedor_id (FK a sellers).

Uso (base real): python migrar_vendedores.py
Demo: set DB_NAME=sistema_inventario_huang_demo && python migrar_vendedores.py
"""
from sqlalchemy import text

from app import create_app
from app.extensions import db

app = create_app()


def main():
    dbname = app.config["DB_NAME"]
    print("Base: " + dbname)
    with app.app_context():
        print("[1] Creando tabla sellers (si falta)...")
        db.create_all()

        with db.engine.connect() as conn:
            existe = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = :db AND table_name = 'sales' AND column_name = 'vendedor_id'"
            ).bindparams(db=dbname)).scalar()
            if not existe:
                conn.execute(text(
                    "ALTER TABLE sales ADD COLUMN vendedor_id INT NULL, "
                    "ADD CONSTRAINT fk_sales_vendedor "
                    "FOREIGN KEY (vendedor_id) REFERENCES sellers(seller_id)"
                ))
                conn.commit()
                print("  + sales.vendedor_id")
            else:
                print("  = sales.vendedor_id ya existe")
        print("Migracion completada.")


if __name__ == "__main__":
    main()
