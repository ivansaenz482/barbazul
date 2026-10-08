from datetime import datetime
from app.extensions import db


class AuditLog(db.Model):
    """Registro de acciones importantes: quién hizo qué y cuándo."""
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    username = db.Column(db.String(50))
    accion = db.Column(db.String(60), nullable=False)
    entidad = db.Column(db.String(40))
    entidad_id = db.Column(db.String(40))
    detalle = db.Column(db.String(500))
    ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship("User")

    def fecha_str(self):
        return self.created_at.strftime("%d/%m/%Y %H:%M:%S") if self.created_at else ""
