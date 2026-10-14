from datetime import datetime

from app.extensions import db


class CajaDia(db.Model):
    """Apertura/cierre de caja por punto (cada usuario maneja su caja/efectivo)."""
    __tablename__ = "caja_dias"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    punto = db.Column(db.String(60))  # nombre del punto de caja (opcional)
    monto_apertura = db.Column(db.Numeric(12, 2), default=0)
    monto_cierre = db.Column(db.Numeric(12, 2))
    notas = db.Column(db.String(255))
    registrado_por = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (db.UniqueConstraint("user_id", "fecha", name="uq_caja_user_fecha"),)
