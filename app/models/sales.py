from datetime import datetime
from app.extensions import db


class Sale(db.Model):
    __tablename__ = "sales"

    sale_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.customer_id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    vendedor_id = db.Column(db.Integer, db.ForeignKey("sellers.seller_id"))
    # Bodega/sucursal desde la que se hizo la venta (de donde se descuenta el stock)
    bodega = db.Column(db.Enum("local", "matriz"), default="local")
    sale_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_type = db.Column(db.Enum("efectivo", "credito"), nullable=False)
    document_type = db.Column(
        db.Enum("factura", "nota_venta_autorizada", "nota_pedido", "proforma"),
        nullable=False, default="nota_venta_autorizada")
    due_date = db.Column(db.Date)
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    total_cost = db.Column(db.Numeric(12, 2), default=0)
    status = db.Column(db.Enum("pendiente", "pagado", "vencido"), default="pendiente")
    liquidada = db.Column(db.Boolean, default=True)
    liquidated_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    liquidated_at = db.Column(db.DateTime)
    dispatch_id = db.Column(db.Integer, db.ForeignKey("dispatch_guides.dispatch_id"))
    sri_status = db.Column(db.Enum("pendiente", "autorizada", "rechazada"), default="pendiente")
    sri_clave_acceso = db.Column(db.String(80))
    sri_autorizado_at = db.Column(db.DateTime)
    sri_autorizado_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))

    customer = db.relationship("Customer", backref="sales")
    seller = db.relationship("User", foreign_keys=[user_id], backref="sales")
    vendedor = db.relationship("Seller", foreign_keys=[vendedor_id], backref="sales")
    liquidator = db.relationship("User", foreign_keys=[liquidated_by])
    details = db.relationship("SaleDetail", backref="sale", cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="sale", cascade="all, delete-orphan")

    def utilidad(self):
        return float(self.total_amount) - float(self.total_cost)

    def pagado_total(self):
        return sum(float(p.amount) for p in self.payments)

    def saldo_pendiente(self):
        return float(self.total_amount) - self.pagado_total()

    def document_type_label(self):
        return {
            "factura": "Factura",
            "nota_venta_autorizada": "Nota de Venta Autorizada",
            "nota_pedido": "Nota de Pedido",
            "proforma": "Proforma",
        }.get(self.document_type, self.document_type)

    def sri_status_label(self):
        return {
            "pendiente": "Pendiente",
            "autorizada": "Autorizada",
            "rechazada": "Rechazada",
        }.get(self.sri_status, "Pendiente")


class SaleDetail(db.Model):
    __tablename__ = "sale_details"

    detail_id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.sale_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False)

    product = db.relationship("Product")

    @property
    def subtotal(self):
        return float(self.quantity) * float(self.unit_price)


class Payment(db.Model):
    __tablename__ = "payments"

    payment_id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.sale_id"), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.Enum("efectivo", "cheque", "transferencia", "tarjeta", "otro"), default="efectivo")
    receipt_number = db.Column(db.String(50))
    registered_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)


class InventoryMovement(db.Model):
    __tablename__ = "inventory_movements"

    movement_id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id"), nullable=False)
    movement_type = db.Column(db.Enum("entrada", "salida", "ajuste"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    reference_type = db.Column(db.Enum("compra", "venta", "ajuste_manual", "pedido_proveedor", "nota_credito"), nullable=False)
    reference_id = db.Column(db.Integer)
    movement_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    notes = db.Column(db.String(255))

    product = db.relationship("Product")
    user = db.relationship("User")
