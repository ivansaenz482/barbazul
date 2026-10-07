from datetime import datetime
import re
from app.extensions import db


class DispatchGuide(db.Model):
    """
    Guia de despacho consolidada para bodega: suma los productos de varias
    ventas (pedidos) seleccionadas en un solo listado por producto, y permite
    agregar productos sueltos por codigo. Es la guia con la que bodega
    prepara y entrega mercaderia.
    """
    __tablename__ = "dispatch_guides"

    dispatch_id = db.Column(db.Integer, primary_key=True)
    dispatch_number = db.Column(db.String(50))
    dispatch_date = db.Column(db.Date, nullable=False)
    origin_branch_id = db.Column(db.Integer, db.ForeignKey("branches.branch_id"))
    transportista_nombre = db.Column(db.String(150))
    transportista_identificacion = db.Column(db.String(20))
    vehiculo_placa = db.Column(db.String(20))
    observaciones = db.Column(db.String(300))
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    entregada = db.Column(db.Boolean, nullable=False, default=False)
    entregada_at = db.Column(db.DateTime)
    entregada_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))

    origin_branch = db.relationship("Branch", foreign_keys=[origin_branch_id])
    creator = db.relationship("User", foreign_keys=[created_by])
    entregada_por_user = db.relationship("User", foreign_keys=[entregada_by])
    details = db.relationship("DispatchGuideDetail", backref="guide", cascade="all, delete-orphan")
    sales = db.relationship("Sale", backref="dispatch_guide", lazy="dynamic")

    def total_ventas(self):
        return len(self.sales.all()) if self.sales else 0

    def total_unidades(self):
        return sum(d.quantity for d in self.details)


class DispatchGuideDetail(db.Model):
    __tablename__ = "dispatch_guide_details"

    detail_id = db.Column(db.Integer, primary_key=True)
    dispatch_id = db.Column(db.Integer, db.ForeignKey("dispatch_guides.dispatch_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    presentacion_snapshot = db.Column(db.String(60))
    unit_measure_snapshot = db.Column(db.String(20))

    product = db.relationship("Product")

    def presentacion(self):
        return self.presentacion_snapshot or (self.product.presentacion if self.product else "unidad")

    def _parse_ml(self):
        """Extrae un numero y unidad tipo '400 ml' de la presentacion. Devuelve (ml, unidad) o (None, None)."""
        texto = (self.presentacion() or "").strip().lower()
        if not texto or texto in ("unidad", "unidades", "un", "u"):
            return None, None
        m = re.match(r"^\s*([\d.]+)\s*([a-z]+)", texto)
        if not m:
            return None, None
        try:
            valor = float(m.group(1))
        except ValueError:
            return None, None
        unidad = m.group(2).replace(".", "")
        return valor, unidad

    def volumen_total_display(self):
        """
        Total de volumen si la presentacion tiene mililitros (ej. 400 ml).
        Ej: 24 unidades x 400 ml -> '9600 ml (9.6 L)'.
        Si no hay mililitraje definido, devuelve None (se muestra solo unidades).
        """
        valor, unidad = self._parse_ml()
        if valor is None:
            return None
        total = self.quantity * valor
        if unidad in ("ml", "mililitros", "mililitro"):
            if total >= 1000:
                return f"{total:,.0f} ml ({total / 1000:.2f} L)".replace(",", " ")
            return f"{total:,.0f} ml".replace(",", " ")
        if unidad in ("l", "lt", "litros", "litro"):
            return f"{total:,.2f} L".replace(",", " ")
        return f"{self.quantity:,.0f} x {self.presentacion()}".replace(",", " ")
