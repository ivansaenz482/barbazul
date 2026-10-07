"""
Migracion para las LISTAS DE PRECIOS (contado / credito / mayorista):
  - products.price_credito, products.price_mayorista
  - customers.price_list

Uso (base real):
    python migrar_listas_precios.py

Para la demo:
    set DB_NAME=sistema_inventario_huang_demo && python migrar_listas_precios.py
"""
from sqlalchemy import text

from app import create_app
from app.extensions import db

app = create_app()


def columna_existe(conn, tabla, columna, dbname):
    return conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = :db AND table_name = :tabla AND column_name = :col"
    ).bindparams(db=dbname, tabla=tabla, col=columna)).scalar()


def main():
    dbname = app.config["DB_NAME"]
    print("Base: " + dbname)
    with app.app_context():
        with db.engine.connect() as conn:
            if not columna_existe(conn, "products", "price_credito", dbname):
                conn.execute(text("ALTER TABLE products ADD COLUMN price_credito DECIMAL(10,2) DEFAULT 0"))
                print("  + products.price_credito")
            else:
                print("  = products.price_credito ya existe")

            if not columna_existe(conn, "products", "price_mayorista", dbname):
                conn.execute(text("ALTER TABLE products ADD COLUMN price_mayorista DECIMAL(10,2) DEFAULT 0"))
                print("  + products.price_mayorista")
            else:
                print("  = products.price_mayorista ya existe")

            if not columna_existe(conn, "customers", "price_list", dbname):
                conn.execute(text(
                    "ALTER TABLE customers ADD COLUMN price_list "
                    "ENUM('contado','credito','mayorista') DEFAULT 'contado'"
                ))
                print("  + customers.price_list")
            else:
                print("  = customers.price_list ya existe")

            conn.commit()
        print("Migracion completada.")


if __name__ == "__main__":
    main()
