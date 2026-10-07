"""
Migracion COMISIONES DE VENDEDORES:
  - Agrega sellers.commission_percent.
  - Crea la tabla commission_payments.
Uso (base real): python migrar_comisiones.py
Demo: set DB_NAME=sistema_inventario_huang_demo && python migrar_comisiones.py
"""
from sqlalchemy import text

from app import create_app
from app.extensions import db

app = create_app()


def col(conn, tabla, columna, dbn):
    return conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema=:db AND table_name=:t AND column_name=:c"
    ).bindparams(db=dbn, t=tabla, c=columna)).scalar()


if __name__ == "__main__":
    dbn = app.config["DB_NAME"]
    print("Base: " + dbn)
    with app.app_context():
        db.create_all()
        with db.engine.connect() as conn:
            if not col(conn, "sellers", "commission_percent", dbn):
                conn.execute(text("ALTER TABLE sellers ADD COLUMN commission_percent DECIMAL(5,2) DEFAULT 0"))
                conn.commit()
                print("  + sellers.commission_percent")
            else:
                print("  = sellers.commission_percent ya existe")
        print("Migracion completada.")
