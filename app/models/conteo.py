from datetime import datetime

from app.extensions import db


class ConteoInventario(db.Model):
    """Sesion de inventario fisico (conteo) por ubicacion."""
    __tablename__ = "conteos_inventario"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120))
    ubicacion = db.Column(db.String(30), default="local")  # local / matriz / sucursal:<id>
    fecha = db.Column(db.Date, nullable=False)
    estado = db.Column(db.Enum("en_proceso", "cerrado"), default="en_proceso")
    notas = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.now)
    cerrado_at = db.Column(db.DateTime)

    user = db.relationship("User")
    detalles = db.relationship("ConteoDetalle", backref="conteo",
                               cascade="all, delete-orphan", lazy=True)

    def total_items(self):
        return len(self.detalles)

    def total_contados(self):
        return sum(1 for d in self.detalles if d.cantidad_contada is not None)

    def total_diferencias(self):
        return sum(1 for d in self.detalles
                   if d.cantidad_contada is not None and d.cantidad_contada != d.stock_sistema)


class ConteoDetalle(db.Model):
    __tablename__ = "conteo_detalles"

    id = db.Column(db.Integer, primary_key=True)
    conteo_id = db.Column(db.Integer, db.ForeignKey("conteos_inventario.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id"), nullable=False)
    stock_sistema = db.Column(db.Integer, default=0)   # foto del stock al iniciar
    cantidad_contada = db.Column(db.Integer)           # lo que se conto fisicamente

    product = db.relationship("Product")

    def diferencia(self):
        if self.cantidad_contada is None:
            return None
        return self.cantidad_contada - self.stock_sistema
