from datetime import datetime
from app.extensions import db


class PushSubscription(db.Model):
    """Suscripcion de un navegador/dispositivo para notificaciones push."""
    __tablename__ = "push_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    endpoint = db.Column(db.String(500), unique=True, nullable=False)
    p256dh = db.Column(db.String(300))
    auth = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship("User")

    def info(self):
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh or "", "auth": self.auth or ""},
        }
