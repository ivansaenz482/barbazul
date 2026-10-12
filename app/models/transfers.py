from datetime import datetime

from app.extensions import db


class StockTransfer(db.Model):
    """Transferencia de stock entre bodegas (Local <-> Matriz)."""
    __tablename__ = "stock_transfers"

    transfer_id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now, nullable=False)
    bodega_origen = db.Column(db.String(20), nullable=False)   # "local" | "matriz"
    bodega_destino = db.Column(db.String(20), nullable=False)  # "local" | "matriz"
    motivo = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)

    user = db.relationship("User")
    details = db.relationship("StockTransferDetail", backref="transfer",
                              cascade="all, delete-orphan", lazy=True)

    def total_unidades(self):
        return sum(d.quantity for d in self.details)

    def origen_label(self):
        from app.stock import etiqueta_ubicacion
        return etiqueta_ubicacion(self.bodega_origen)

    def destino_label(self):
        from app.stock import etiqueta_ubicacion
        return etiqueta_ubicacion(self.bodega_destino)


class StockTransferDetail(db.Model):
    __tablename__ = "stock_transfer_details"

    detail_id = db.Column(db.Integer, primary_key=True)
    transfer_id = db.Column(db.Integer, db.ForeignKey("stock_transfers.transfer_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    product = db.relationship("Product")
