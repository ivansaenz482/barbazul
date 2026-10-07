"""
Migracion: agrega supplier_orders.purchase_invoice_id (vinculo pedido -> compra).

Uso (base real):
    python migrar_convertir_pedido.py
Para la demo:
    set DB_NAME=sistema_inventario_huang_demo && python migrar_convertir_pedido.py
"""
from sqlalchemy import text

from app import create_app
from app.extensions import db

app = create_app()


def main():
    dbname = app.config["DB_NAME"]
    print("Base: " + dbname)
    with app.app_context():
        with db.engine.connect() as conn:
            existe = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = :db AND table_name = 'supplier_orders' "
                "AND column_name = 'purchase_invoice_id'"
            ).bindparams(db=dbname)).scalar()
            if not existe:
                conn.execute(text(
                    "ALTER TABLE supplier_orders ADD COLUMN purchase_invoice_id INT NULL, "
                    "ADD CONSTRAINT fk_supplier_orders_invoice "
                    "FOREIGN KEY (purchase_invoice_id) REFERENCES purchase_invoices(invoice_id)"
                ))
                conn.commit()
                print("  + supplier_orders.purchase_invoice_id")
            else:
                print("  = supplier_orders.purchase_invoice_id ya existe")
        print("Migracion completada.")


if __name__ == "__main__":
    main()
