from datetime import datetime
from flask_login import UserMixin
from app.extensions import db, login_manager


user_categories = db.Table(
    "user_categories",
    db.Column("user_id", db.Integer, db.ForeignKey("users.user_id"), primary_key=True),
    db.Column("category_id", db.Integer, db.ForeignKey("categories.category_id"), primary_key=True),
)


class Role(db.Model):
    __tablename__ = "roles"

    role_id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(30), unique=True, nullable=False)

    users = db.relationship("User", backref="role", lazy=True)


class User(db.Model, UserMixin):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    role_id = db.Column(db.Integer, db.ForeignKey("roles.role_id"), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    avatar_path = db.Column(db.String(300))

    # Bodega/sucursal asignada. "local" o "matriz". Si es NULL (ej. admin),
    # el usuario puede operar/ver las dos bodegas.
    bodega = db.Column(db.Enum("local", "matriz"))

    # Permisos granulares (solo aplican si no es administrador; el admin siempre tiene todo)
    perm_inventario = db.Column(db.Boolean, default=False)
    perm_ventas = db.Column(db.Boolean, default=False)
    perm_clientes = db.Column(db.Boolean, default=False)
    perm_edit_stock = db.Column(db.Boolean, default=False)
    perm_edit_pedidos = db.Column(db.Boolean, default=False)
    perm_reporte_caja = db.Column(db.Boolean, default=False)

    def initials(self):
        partes = self.full_name.strip().split()
        if len(partes) >= 2:
            return (partes[0][0] + partes[-1][0]).upper()
        return self.full_name[:2].upper() if self.full_name else "?"

    # Categorias que este vendedor tiene permitido vender.
    # Si la lista esta vacia, se le permite vender TODAS las categorias (sin restriccion).
    allowed_categories = db.relationship(
        "Category", secondary=user_categories, backref="allowed_users", lazy="joined"
    )

    def can_sell_category(self, category_id):
        """El administrador siempre puede todo. Un vendedor sin restricciones tambien puede todo."""
        if self.is_admin():
            return True
        if not self.allowed_categories:
            return True
        return any(c.category_id == category_id for c in self.allowed_categories)

    # Flask-Login necesita un id unico como string
    def get_id(self):
        return str(self.user_id)

    def is_admin(self):
        return self.role.role_name == "administrador"

    # Helpers de permisos: el administrador siempre tiene todos los permisos
    def can_view_inventario(self):
        return self.is_admin() or bool(self.perm_inventario)

    def can_edit_stock(self):
        return self.is_admin() or bool(self.perm_edit_stock)

    def can_view_ventas(self):
        return self.is_admin() or bool(self.perm_ventas)

    def can_edit_pedidos(self):
        return self.is_admin() or bool(self.perm_edit_pedidos)

    def can_view_clientes(self):
        return self.is_admin() or bool(self.perm_clientes)

    def can_view_reporte_caja(self):
        return self.is_admin() or bool(self.perm_reporte_caja)

    # --- Bodega / sucursal ---
    def ve_todas_bodegas(self):
        """El admin y los usuarios sin bodega asignada ven/operan las dos bodegas."""
        return self.is_admin() or self.bodega is None

    def bodega_label(self):
        return {"local": "Bodega Local", "matriz": "Bodega Matriz"}.get(self.bodega, "Todas las bodegas")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Supplier(db.Model):
    __tablename__ = "suppliers"

    supplier_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    ruc = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.String(200))
    credit_term_days = db.Column(db.Enum("0", "30", "60", "90"), default="0")

    products = db.relationship("Product", backref="supplier", lazy=True)

    def term_label(self):
        return {
            "0": "Contado",
            "30": "30 días",
            "60": "60 días",
            "90": "90 días (3 meses)",
        }.get(self.credit_term_days, "Contado")


class Category(db.Model):
    __tablename__ = "categories"

    category_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))

    products = db.relationship("Product", backref="category", lazy=True)


class Product(db.Model):
    __tablename__ = "products"

    product_id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True)
    barcode = db.Column(db.String(60), index=True)
    name = db.Column(db.String(150), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.category_id"))
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.supplier_id"))
    unit_measure = db.Column(db.String(20), default="unidad")
    presentacion = db.Column(db.String(60), default="unidad")
    cost_price = db.Column(db.Numeric(10, 2), default=0)
    sale_price = db.Column(db.Numeric(10, 2), default=0)
    # Listas de precios: contado (sale_price), credito y mayorista
    price_credito = db.Column(db.Numeric(10, 2), default=0)
    price_mayorista = db.Column(db.Numeric(10, 2), default=0)
    min_stock = db.Column(db.Integer, default=0)
    max_stock = db.Column(db.Integer, default=0)
    current_stock = db.Column(db.Integer, default=0)
    # Stock de la bodega MATRIZ (bodega principal). El current_stock se mantiene
    # como el stock de la bodega LOCAL (donde se venden los productos).
    stock_matriz = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    image_path = db.Column(db.String(300))

    def total_stock(self):
        """Stock total: bodega local (current_stock) + bodega matriz."""
        return (self.current_stock or 0) + (self.stock_matriz or 0)

    def stock_status(self):
        """Devuelve el estado del stock para mostrar semaforo en el dashboard"""
        if self.total_stock() <= self.min_stock:
            return "bajo"
        if self.max_stock and self.total_stock() >= self.max_stock:
            return "sobre"
        return "normal"

    def precio_lista(self, lista):
        """
        Devuelve el precio segun la lista elegida ('contado', 'credito', 'mayorista').
        Si la lista especifica no tiene precio (0 o vacio), usa el precio de contado.
        """
        if lista == "credito":
            valor = self.price_credito
        elif lista == "mayorista":
            valor = self.price_mayorista
        else:
            valor = self.sale_price
        return float(valor) if valor else float(self.sale_price or 0)


class Branch(db.Model):
    __tablename__ = "branches"
    branch_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    active = db.Column(db.Boolean, default=True)

    customers = db.relationship("Customer", backref="branch", lazy=True)


class Customer(db.Model):
    __tablename__ = "customers"

    customer_id = db.Column(db.Integer, primary_key=True)
    cedula = db.Column(db.String(20), unique=True)
    full_name = db.Column(db.String(150), nullable=False)
    business_name = db.Column(db.String(150))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.String(200))
    province = db.Column(db.String(50))
    city = db.Column(db.String(50))
    customer_type = db.Column(db.Enum("efectivo", "credito"), default="efectivo")
    # Lista de precios que se le aplica al cliente al vender
    price_list = db.Column(db.Enum("contado", "credito", "mayorista"), default="contado")
    credit_limit = db.Column(db.Numeric(12, 2), default=0)
    credit_term_days = db.Column(db.Enum("0", "30", "60", "90"), default="0")
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.branch_id"))
    active = db.Column(db.Boolean, default=True)


class CompanySetting(db.Model):
    """Configuracion general del negocio (por ahora, el logo)."""
    __tablename__ = "company_settings"

    id = db.Column(db.Integer, primary_key=True)
    logo_path = db.Column(db.String(300))

    @classmethod
    def actual(cls):
        """Devuelve la fila unica de configuracion (o None si aun no existe)."""
        return cls.query.first()


class Seller(db.Model):
    """Vendedor (catalogo administrado por el administrador)."""
    __tablename__ = "sellers"

    seller_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20))
    commission_percent = db.Column(db.Numeric(5, 2), default=0)  # % de comision sobre las ventas
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)


class CommissionPayment(db.Model):
    """Pago de comisiones a un vendedor (por periodo)."""
    __tablename__ = "commission_payments"

    payment_id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("sellers.seller_id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(12, 2), default=0)
    periodo = db.Column(db.String(30))
    notas = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.now)

    seller = db.relationship("Seller")


class SalesGoal(db.Model):
    """Meta de ventas por mes. Puede ser global, por vendedor o por bodega."""
    __tablename__ = "sales_goals"

    goal_id = db.Column(db.Integer, primary_key=True)
    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    meta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    seller_id = db.Column(db.Integer, db.ForeignKey("sellers.seller_id"))  # NULL = todos los vendedores
    bodega = db.Column(db.Enum("local", "matriz"))                        # NULL = ambas bodegas
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.now)

    seller = db.relationship("Seller")

    def alcance_label(self):
        partes = []
        partes.append(self.seller.name if self.seller else "Todos los vendedores")
        partes.append("Bodega Matriz" if self.bodega == "matriz" else ("Bodega Local" if self.bodega == "local" else "Ambas bodegas"))
        return " · ".join(partes)
