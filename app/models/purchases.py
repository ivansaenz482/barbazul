from datetime import datetime, date
from app.extensions import db


class PurchaseInvoice(db.Model):
    __tablename__ = "purchase_invoices"

    invoice_id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.supplier_id"), nullable=False)
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.Date, nullable=False)
    source_type = db.Column(db.Enum("manual", "pdf", "imagen"), nullable=False, default="manual")
    file_path = db.Column(db.String(300))
    ocr_raw_text = db.Column(db.Text)
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    payment_type = db.Column(db.Enum("efectivo", "credito"), default="efectivo")
    due_date = db.Column(db.Date)
    status = db.Column(db.Enum("pendiente", "pagado", "vencido"), default="pendiente")
    registered_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    supplier = db.relationship("Supplier", backref="purchase_invoices")
    registered_by_user = db.relationship("User", backref="purchase_invoices")
    details = db.relationship("PurchaseInvoiceDetail", backref="invoice", cascade="all, delete-orphan")
    payments = db.relationship("SupplierPayment", backref="invoice", cascade="all, delete-orphan")

    def pagado_total(self):
        return sum(float(p.amount) for p in self.payments)

    def saldo_pendiente(self):
        return float(self.total_amount or 0) - self.pagado_total()

    def estado_actual(self):
        """Estado considerando vencimiento: pagado, vencido o pendiente."""
        if self.status == "pagado":
            return "pagado"
        if self.due_date and self.due_date < date.today() and self.saldo_pendiente() > 0:
            return "vencido"
        return "pendiente"

    def estado_label(self):
        return {
            "pagado": "Pagado",
            "vencido": "Vencido",
            "pendiente": "Pendiente",
        }.get(self.estado_actual(), self.status)


class PurchaseInvoiceDetail(db.Model):
    __tablename__ = "purchase_invoice_details"

    detail_id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("purchase_invoices.invoice_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False)

    product = db.relationship("Product")

    @property
    def subtotal(self):
        return float(self.quantity) * float(self.unit_cost)


class SupplierPayment(db.Model):
    __tablename__ = "supplier_payments"

    payment_id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("purchase_invoices.invoice_id"), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.now)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.Enum("efectivo", "cheque", "transferencia", "tarjeta", "otro"), default="efectivo")
    receipt_number = db.Column(db.String(50))
    notes = db.Column(db.String(255))
    registered_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)

    registered_by_user = db.relationship("User", backref="supplier_payments")

    def metodo_label(self):
        return {
            "efectivo": "Efectivo",
            "cheque": "Cheque",
            "transferencia": "Transferencia",
            "tarjeta": "Tarjeta",
            "otro": "Otro",
        }.get(self.payment_method, self.payment_method)


class SupplierOrder(db.Model):
    """
    Pedido a proveedor (orden de compra). Sirve para solicitar mercaderia al
    proveedor e imprimir/enviar el documento. Al crearse suma el stock a la
    bodega elegida. Solo el administrador puede crearlo, editarlo o eliminarlo.
    """
    __tablename__ = "supplier_orders"

    order_id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50))
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.supplier_id"), nullable=False)
    order_date = db.Column(db.Date, nullable=False)
    bodega_destino = db.Column(db.Enum("local", "matriz"), default="local")
    status = db.Column(db.Enum("borrador", "enviado", "recibido", "anulado"), default="borrador")
    notes = db.Column(db.Text)
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Si el pedido ya fue convertido en una factura de compra
    purchase_invoice_id = db.Column(db.Integer, db.ForeignKey("purchase_invoices.invoice_id"))

    supplier = db.relationship("Supplier", backref="supplier_orders")
    creator = db.relationship("User", backref="supplier_orders")
    purchase_invoice = db.relationship("PurchaseInvoice", foreign_keys=[purchase_invoice_id])
    details = db.relationship("SupplierOrderDetail", backref="order", cascade="all, delete-orphan")

    def convertido(self):
        return self.purchase_invoice_id is not None

    def codigo(self):
        return self.order_number or f"PED-{self.order_id:05d}"

    def total_unidades(self):
        return sum(d.quantity for d in self.details)

    def status_label(self):
        return {
            "borrador": "Borrador",
            "enviado": "Enviado",
            "recibido": "Recibido",
            "anulado": "Anulado",
        }.get(self.status, self.status)

    def bodega_label(self):
        return "Bodega Matriz" if self.bodega_destino == "matriz" else "Bodega Local"


class SupplierOrderDetail(db.Model):
    __tablename__ = "supplier_order_details"

    detail_id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("supplier_orders.order_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False)

    product = db.relationship("Product")

    @property
    def subtotal(self):
        return float(self.quantity) * float(self.unit_cost)
