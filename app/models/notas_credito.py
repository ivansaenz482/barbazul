from datetime import datetime
from app.extensions import db


class NotaCredito(db.Model):
    """
    Nota de Crédito (codDoc 04 del SRI). Se emite para devolver/descontar
    total o parcialmente una venta. Devuelve el stock a la bodega original.
    """
    __tablename__ = "notas_credito"

    nc_id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30))
    fecha = db.Column(db.Date, nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.sale_id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.customer_id"))
    motivo = db.Column(db.Enum("devolucion", "descuento", "error", "otro"), default="devolucion")
    bodega = db.Column(db.Enum("local", "matriz"), default="local")
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    valor_iva = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    observaciones = db.Column(db.String(255))
    sri_clave_acceso = db.Column(db.String(80))
    sri_status = db.Column(db.Enum("pendiente", "autorizada", "rechazada"), default="pendiente")
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sale = db.relationship("Sale")
    customer = db.relationship("Customer")
    creator = db.relationship("User", foreign_keys=[created_by])
    details = db.relationship("NotaCreditoDetail", backref="nota", cascade="all, delete-orphan")

    def total_unidades(self):
        return sum(d.quantity for d in self.details)

    def motivo_label(self):
        return {
            "devolucion": "Devolución de mercadería",
            "descuento": "Descuento posterior",
            "error": "Corrección por error",
            "otro": "Otro",
        }.get(self.motivo, self.motivo)

    def sri_status_label(self):
        return {"pendiente": "Pendiente", "autorizada": "Autorizada", "rechazada": "Rechazada"}.get(
            self.sri_status, self.sri_status)


class NotaCreditoDetail(db.Model):
    __tablename__ = "notas_credito_detalles"

    detail_id = db.Column(db.Integer, primary_key=True)
    nc_id = db.Column(db.Integer, db.ForeignKey("notas_credito.nc_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False)

    product = db.relationship("Product")

    @property
    def subtotal(self):
        return float(self.quantity) * float(self.unit_price)
