"""
Migracion MULTI-BODEGA:
  - users.bodega  (ENUM local/matriz, NULL = ve ambas)
  - sales.bodega  (ENUM local/matriz, de donde se descuenta el stock)
Uso (base real): python migrar_bodegas.py
Demo: set DB_NAME=sistema_inventario_huang_demo && python migrar_bodegas.py
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


def main():
    dbn = app.config["DB_NAME"]
    print("Base: " + dbn)
    with app.app_context():
        with db.engine.connect() as conn:
            if not col(conn, "users", "bodega", dbn):
                conn.execute(text("ALTER TABLE users ADD COLUMN bodega ENUM('local','matriz') NULL"))
                print("  + users.bodega")
            else:
                print("  = users.bodega ya existe")
            if not col(conn, "sales", "bodega", dbn):
                conn.execute(text("ALTER TABLE sales ADD COLUMN bodega ENUM('local','matriz') DEFAULT 'local'"))
                print("  + sales.bodega")
            else:
                print("  = sales.bodega ya existe")
            conn.commit()
        print("Migracion completada.")


if __name__ == "__main__":
    main()
