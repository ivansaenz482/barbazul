"""
Script para INICIALIZAR la base de datos NUEVA del proyecto.

Crea la base de datos (si no existe), crea TODAS las tablas y agrega los
datos base: roles (administrador, personal) y las categorias del negocio
(llantas, luces, baterias, accesorios).

Uso:
    python init_db.py

OJO: solo ejecutalo la primera vez (o cuando quieras re-crear la base vacia).
Este script NO borra tablas existentes; solo crea lo que falte y agrega
roles/categorias que no existan todavia.
"""
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app import create_app
from app.extensions import db
from app.models import Role, Category

app = create_app()

CATEGORIAS_DEFECTO = [
    ("llantas", "Llantas y neumáticos"),
    ("luces", "Luces e iluminación"),
    ("baterias", "Baterías y acumuladores"),
    ("accesorios", "Accesorios y repuestos"),
]

ROLES_DEFECTO = ["administrador", "personal"]


def crear_base_si_no_existe():
    """Crea la base de datos en MySQL si aun no existe."""
    db_name = app.config["DB_NAME"]
    host = app.config["DB_HOST"]
    port = app.config["DB_PORT"]
    user = app.config["DB_USER"]
    password = app.config["DB_PASSWORD"]

    print(f"[1/4] Verificando que la base '{db_name}' exista en MySQL...")
    url_sin_db = f"mysql+pymysql://{user}:{password}@{host}:{port}/mysql"
    try:
        engine = create_engine(url_sin_db)
        with engine.connect() as conn:
            fila = conn.execute(text(
                f"SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = '{db_name}'"
            )).scalar()
            if not fila:
                conn.execute(text(
                    f"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                ))
                print(f"    Base '{db_name}' creada correctamente.")
            else:
                print(f"    La base '{db_name}' ya existia.")
        engine.dispose()
    except OperationalError as e:
        print("    ERROR: No se pudo conectar a MySQL. Revisa DB_USER/DB_PASSWORD/DB_HOST en .env")
        print(f"    Detalle: {e}")
        sys.exit(1)


def crear_tablas():
    print("[2/4] Creando las tablas del sistema (puede tardar unos segundos)...")
    db.create_all()

    # Asegurar la columna de stock de matriz (por si la tabla ya existia antes
    # de que el modelo la incluyera).
    from sqlalchemy import text as _text
    with db.engine.connect() as conn:
        col_existe = conn.execute(_text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = :db AND table_name = 'products' AND column_name = 'stock_matriz'"
        ).bindparams(db=app.config["DB_NAME"])).scalar()
        if not col_existe:
            conn.execute(_text("ALTER TABLE products ADD COLUMN stock_matriz INT DEFAULT 0"))
            print("    Columna 'stock_matriz' agregada a la tabla products.")
    print("    Tablas creadas o ya existentes.")


def sembrar_roles():
    print("[3/4] Agregando roles base...")
    for nombre in ROLES_DEFECTO:
        if not Role.query.filter_by(role_name=nombre).first():
            db.session.add(Role(role_name=nombre))
            print(f"    Rol '{nombre}' agregado.")
    db.session.commit()


def sembrar_categorias():
    print("[4/4] Agregando categorias del negocio...")
    for nombre, desc in CATEGORIAS_DEFECTO:
        if not Category.query.filter_by(name=nombre).first():
            db.session.add(Category(name=nombre, description=desc))
            print(f"    Categoria '{nombre}' agregada.")
    db.session.commit()


if __name__ == "__main__":
    with app.app_context():
        crear_base_si_no_existe()
        crear_tablas()
        sembrar_roles()
        sembrar_categorias()
        print("\nListo. Base de datos inicializada.")
        print("Ahora crea el usuario administrador con:  python crear_admin.py")