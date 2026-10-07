"""
Script para preparar un entorno DEMO del sistema (base de datos aparte)
con datos ficticios. NO toca la base real del negocio.

Crea la base 'sistema_inventario_huang_demo', sus tablas, un usuario demo
y datos de ejemplo (productos, clientes, ventas, guias de despacho) para
que un cliente pruebe el sistema y vea reportes con informacion.

Uso:
    python setup_demo.py
"""
import os
import sys
from datetime import datetime, timedelta

# IMPORTANTE: fijamos la base DEMO ANTES de importar el resto.
os.environ["DB_NAME"] = "sistema_inventario_huang_demo"

import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app import create_app
from app.extensions import db
from app.models import (Role, User, Supplier, Category, Product, Customer, Branch,
                        Sale, SaleDetail, Payment, DispatchGuide, DispatchGuideDetail)

app = create_app()

DEMO_PASSWORD = "demo123"

ROL_ADMIN = "administrador"

CATEGORIAS = [
    ("llantas", "Llantas y neumáticos"),
    ("luces", "Luces e iluminación"),
    ("baterias", "Baterías y acumuladores"),
    ("accesorios", "Accesorios y repuestos"),
]

SUPPLIERS = [
    ("Llantas del Pacífico S.A.", "0999999999001"),
    ("Súper Baterías Andinas", "0999999999002"),
    ("Iluminación Pro", "0999999999003"),
]

BRANCHES = [
    ("Matriz", "Av. Principal y 10 de Agosto, Guayaquil", "0999999000"),
]

PRODUCTS = [
    # sku, barcode, name, category, supplier, cost, price, unit, presentacion, stock
    ("LL-205-45", "7751234012301", "Llanta 205/45 R17", "llantas", "Llantas del Pacífico S.A.", 55.00, 78.00, "unidad", "unidad", 40),
    ("LL-195-65", "7751234012318", "Llanta 195/65 R15", "llantas", "Llantas del Pacífico S.A.", 48.00, 68.00, "unidad", "unidad", 35),
    ("LL-10-16", "7751234012325", "Llanta 100/80 R12", "llantas", "Llantas del Pacífico S.A.", 25.00, 38.00, "unidad", "unidad", 60),
    ("BA-12-75", "7751234012332", "Batería 12V 75Ah", "baterias", "Súper Baterías Andinas", 70.00, 98.00, "unidad", "unidad", 25),
    ("BA-12-40", "7751234012349", "Batería 12V 40Ah", "baterias", "Súper Baterías Andinas", 55.00, 76.00, "unidad", "unidad", 30),
    ("LU-H7", "7751234012356", "Lámpara LED H7", "luces", "Iluminación Pro", 12.00, 20.00, "unidad", "unidad", 80),
    ("LU-H4", "7751234012363", "Lámpara Halógena H4", "luces", "Iluminación Pro", 8.00, 14.00, "unidad", "unidad", 90),
    ("AC-ACE10", "7751234012370", "Aceite Motor 10W-30 1L", "accesorios", "Iluminación Pro", 6.50, 11.00, "unidad", "1000 ml", 120),
    ("AC-FILT", "7751234012387", "Filtro de Aire Universal", "accesorios", "Llantas del Pacífico S.A.", 7.00, 12.50, "unidad", "unidad", 65),
    ("AC-BUJ", "7751234012394", "Bujía NGK", "accesorios", "Súper Baterías Andinas", 3.50, 7.00, "unidad", "unidad", 150),
    ("LU-LED-BAR", "7751234012400", "Barra LED 150W", "luces", "Iluminación Pro", 45.00, 72.00, "unidad", "unidad", 20),
    ("AL-205-45", "7751234012417", "Llantas 225/45 R18", "llantas", "Llantas del Pacífico S.A.", 62.00, 90.00, "unidad", "unidad", 30),
]

CUSTOMERS = [
    # cedula, full_name, business_name, phone, province, city, type, credit_term
    ("0912345678", "Juan Pérez Valdez", "Taller Pérez", "0987654321", "Guayas", "Guayaquil", "credito", "30"),
    ("0923456789", "María Rodríguez Soto", "Auto Repuestos Mary", "0998765432", "Guayas", "Samborondón", "credito", "60"),
    ("0934567890", "Carlos Andrade Lima", None, "0961112223", "Azuay", "Cuenca", "efectivo", "0"),
    ("0945678901", "Ana Vélez Castro", "Mecánica Ana", "0952223334", "Pichincha", "Quito", "efectivo", "0"),
    ("0956789012", "Luis Zambrano Díaz", None, "0993334445", "Manabí", "Manta", "credito", "30"),
    ("0967890123", "Elena Mora Ríos", "Eléctricos Mora", "0984445556", "Guayas", "Daule", "efectivo", "0"),
    ("0978901234", "Pedro Cuesta Núñez", None, "0975556667", "Los Ríos", "Babahoyo", "credito", "60"),
    ("0989012345", "Sofía Palacios Serna", "ServiCar Palacios", "0966667778", "El Oro", "Machala", "efectivo", "0"),
]


def crear_base_si_no_existe():
    db_name = app.config["DB_NAME"]
    host = app.config["DB_HOST"]
    port = app.config["DB_PORT"]
    user = app.config["DB_USER"]
    password = app.config["DB_PASSWORD"]
    print(f"[0] Verificando base '{db_name}'...")
    url_sin_db = f"mysql+pymysql://{user}:{password}@{host}:{port}/mysql"
    engine = create_engine(url_sin_db)
    with engine.connect() as conn:
        fila = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = :n"
        ).bindparams(n=db_name)).scalar()
        if not fila:
            conn.execute(text(
                f"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            ))
            print(f"    Base '{db_name}' creada.")
        else:
            print(f"    Base '{db_name}' ya existia (no se recrea; se reutiliza).")
    engine.dispose()


def main():
    crear_base_si_no_existe()
    with app.app_context():
        print("[1] Creando tablas...")
        db.create_all()

        print("[2] Roles y categorias...")
        for nombre in ["administrador", "personal"]:
            if not Role.query.filter_by(role_name=nombre).first():
                db.session.add(Role(role_name=nombre))
        cat_map = {}
        for nombre, desc in CATEGORIAS:
            cat = Category.query.filter_by(name=nombre).first()
            if not cat:
                cat = Category(name=nombre, description=desc)
                db.session.add(cat)
                db.session.flush()
            cat_map[nombre] = cat

        print("[3] Bodega / Sucursal...")
        branch = Branch.query.filter_by(name="Matriz").first()
        if not branch:
            branch = Branch(name="Matriz", address=BRANCHES[0][1], phone=BRANCHES[0][2])
            db.session.add(branch)
            db.session.flush()

        print("[4] Proveedores...")
        sup_map = {}
        for nombre, ruc in SUPPLIERS:
            sup = Supplier.query.filter_by(name=nombre).first()
            if not sup:
                sup = Supplier(name=nombre, ruc=ruc)
                db.session.add(sup)
                db.session.flush()
            sup_map[nombre] = sup

        print("[5] Productos de ejemplo...")
        prod_map = {}
        for sku, barcode, name, cat, sup, cost, price, unit, pres, stock in PRODUCTS:
            p = Product.query.filter_by(sku=sku).first()
            if not p:
                p = Product(
                    sku=sku, barcode=barcode, name=name,
                    category_id=cat_map[cat].category_id,
                    supplier_id=sup_map[sup].supplier_id,
                    unit_measure=unit, presentacion=pres,
                    cost_price=cost, sale_price=price,
                    current_stock=stock, stock_matriz=stock,
                    active=True,
                )
                db.session.add(p)
                db.session.flush()
            prod_map[name] = p

        print("[6] Clientes de ejemplo...")
        cust_map = {}
        for cedula, name, biz, phone, prov, city, tipo, term in CUSTOMERS:
            c = Customer.query.filter_by(cedula=cedula).first()
            if not c:
                c = Customer(
                    cedula=cedula, full_name=name, business_name=biz, phone=phone,
                    province=prov, city=city, customer_type=tipo,
                    credit_term_days=term, credit_limit=1000 if tipo == "credito" else 0,
                    branch_id=branch.branch_id, active=True,
                )
                db.session.add(c)
                db.session.flush()
            cust_map[name] = c

        print("[7] Usuario demo...")
        demo = User.query.filter_by(username="demo").first()
        if not demo:
            admin = Role.query.filter_by(role_name=ROL_ADMIN).first()
            pwd = bcrypt.hashpw(DEMO_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            demo = User(
                username="demo", password_hash=pwd,
                full_name="Usuario Demo BarbaZul",
                role_id=admin.role_id, active=True,
            )
            db.session.add(demo)
            db.session.flush()
        print(f"    Usuario 'demo' / '{DEMO_PASSWORD}' (rol {ROL_ADMIN}).")

        print("[8] Ventas de ejemplo (ultimos 45 dias)...")
        if Sale.query.count() == 0:
            now = datetime.utcnow()
            # (dias_atras, cliente, [(producto_name, qty)], tipo_pago, estado)
            PLAN = [
                (44, "Juan Pérez Valdez", [("Llanta 205/45 R17", 4)], "credito", "pagado"),
                (40, "María Rodríguez Soto", [("Batería 12V 75Ah", 2)], "credito", "pagado"),
                (38, "Carlos Andrade Lima", [("Lámpara LED H7", 6)], "efectivo", "pagado"),
                (35, "Ana Vélez Castro", [("Aceite Motor 10W-30 1L", 10)], "efectivo", "pagado"),
                (33, "Luis Zambrano Díaz", [("Llanta 195/65 R15", 4), ("Bujía NGK", 4)], "credito", "pendiente"),
                (28, "Elena Mora Ríos", [("Filtro de Aire Universal", 5)], "efectivo", "pagado"),
                (24, "Pedro Cuesta Núñez", [("Batería 12V 40Ah", 2)], "credito", "pendiente"),
                (20, "Sofía Palacios Serna", [("Lámpara Halógena H4", 8)], "efectivo", "pagado"),
                (16, "Juan Pérez Valdez", [("Llanta 225/45 R18", 4), ("Barra LED 150W", 2)], "efectivo", "pagado"),
                (12, "María Rodríguez Soto", [("Aceite Motor 10W-30 1L", 6)], "credito", "pendiente"),
                (8, "Carlos Andrade Lima", [("Bujía NGK", 10)], "efectivo", "pagado"),
                (5, "Ana Vélez Castro", [("Llanta 100/80 R12", 6), ("Lámpara LED H7", 2)], "efectivo", "pagado"),
                (2, "Luis Zambrano Díaz", [("Batería 12V 75Ah", 3)], "credito", "pendiente"),
                (1, "Elena Mora Ríos", [("Lámpara Halógena H4", 4), ("Filtro de Aire Universal", 2)], "efectivo", "pagado"),
                (0, "Sofía Palacios Serna", [("Aceite Motor 10W-30 1L", 4), ("Bujía NGK", 2)], "efectivo", "pagado"),
            ]
            for dias, cli_nombre, items, forma, estado in PLAN:
                c = cust_map[cli_nombre]
                if not c:
                    continue
                fecha = now - timedelta(days=dias)
                v = Sale(
                    customer_id=c.customer_id, user_id=demo.user_id,
                    sale_date=fecha,
                    payment_type=forma, document_type="nota_venta_autorizada",
                    status=estado, liquidada=True,
                    liquidated_by=demo.user_id, liquidated_at=fecha,
                )
                db.session.add(v)
                db.session.flush()
                total = 0.0
                total_cost = 0.0
                for prod_name, qty in items:
                    p = prod_map.get(prod_name)
                    if not p:
                        continue
                    up = float(p.sale_price)
                    db.session.add(SaleDetail(
                        sale_id=v.sale_id, product_id=p.product_id, quantity=qty,
                        unit_price=up, unit_cost=float(p.cost_price),
                    ))
                    p.current_stock = (p.current_stock or 0) - qty
                    total += up * qty
                    total_cost += float(p.cost_price) * qty
                v.total_amount = round(total, 2)
                v.total_cost = round(total_cost, 2)
                if estado == "pagado":
                    db.session.add(Payment(
                        sale_id=v.sale_id, amount=round(total, 2),
                        payment_method="efectivo", registered_by=demo.user_id, payment_date=fecha,
                    ))
            print(f"    {len(PLAN)} ventas creadas.")
        else:
            print("    Ya hay ventas en la base demo; se omiten.")

        print("[9] Guia de despacho de ejemplo...")
        if DispatchGuide.query.count() == 0:
            guia = DispatchGuide(
                dispatch_number="GUIA-0001",
                dispatch_date=datetime.utcnow().date(),
                origin_branch_id=branch.branch_id,
                transportista_nombre="Transportes Rápidos del Sur",
                transportista_identificacion="0912345678",
                vehiculo_placa="GKE-1234",
                observaciones="Guía de ejemplo para demostración.",
                created_by=demo.user_id,
                entregada=False,
            )
            db.session.add(guia)
            db.session.flush()
            for prod in list(prod_map.values())[:4]:
                db.session.add(DispatchGuideDetail(
                    dispatch_id=guia.dispatch_id, product_id=prod.product_id,
                    quantity=4, presentacion_snapshot=prod.presentacion,
                    unit_measure_snapshot=prod.unit_measure,
                ))
            print("    Guía GUIA-0001 creada.")

        db.session.commit()
        print("")
        print("[OK] Ambiente DEMO listo.")
        print("   - Base:      " + app.config["DB_NAME"])
        print("   - Usuario:   demo / " + DEMO_PASSWORD)
        print("   - Ejecutar:  python run_demo.py  (abre en http://127.0.0.1:5011)")


if __name__ == "__main__":
    main()
