from datetime import datetime
from app.extensions import db


class DeliveryGuide(db.Model):
    __tablename__ = "delivery_guides"

    guide_id = db.Column(db.Integer, primary_key=True)
    guide_number = db.Column(db.String(50))
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.sale_id"))
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.customer_id"))
    origin_branch_id = db.Column(db.Integer, db.ForeignKey("branches.branch_id"))
    destination_branch_id = db.Column(db.Integer, db.ForeignKey("branches.branch_id"))
    destination_address = db.Column(db.String(200))
    motivo = db.Column(db.Enum("venta", "traslado_interno", "devolucion", "otro"), nullable=False, default="venta")
    transportista_nombre = db.Column(db.String(150))
    transportista_identificacion = db.Column(db.String(20))
    vehiculo_placa = db.Column(db.String(20))
    fecha_emision = db.Column(db.Date, nullable=False)
    observaciones = db.Column(db.String(300))
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    entregada = db.Column(db.Boolean, nullable=False, default=False)
    entregada_at = db.Column(db.DateTime)
    entregada_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))

    sale = db.relationship("Sale", backref="delivery_guides")
    customer = db.relationship("Customer")
    origin_branch = db.relationship("Branch", foreign_keys=[origin_branch_id])
    destination_branch = db.relationship("Branch", foreign_keys=[destination_branch_id])
    creator = db.relationship("User", foreign_keys=[created_by])
    entregada_por_user = db.relationship("User", foreign_keys=[entregada_by])
    details = db.relationship("DeliveryGuideDetail", backref="guide", cascade="all, delete-orphan")

    def motivo_label(self):
        return {
            "venta": "Entrega por venta",
            "traslado_interno": "Traslado interno entre locales",
            "devolucion": "Devolución",
            "otro": "Otro",
        }.get(self.motivo, self.motivo)


class DeliveryGuideDetail(db.Model):
    __tablename__ = "delivery_guide_details"

    detail_id = db.Column(db.Integer, primary_key=True)
    guide_id = db.Column(db.Integer, db.ForeignKey("delivery_guides.guide_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    product = db.relationship("Product")
