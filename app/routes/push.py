from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.models import PushSubscription

push_bp = Blueprint("push", __name__, url_prefix="/push")


@push_bp.route("/public-key")
def public_key():
    return jsonify({"publicKey": current_app.config.get("VAPID_PUBLIC_KEY", "")})


@push_bp.route("/subscribe", methods=["POST"])
@login_required
def subscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys") or {}
    if not endpoint:
        return jsonify({"ok": False, "error": "endpoint vacío"}), 400
    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not sub:
        sub = PushSubscription(endpoint=endpoint)
        db.session.add(sub)
    sub.user_id = current_user.user_id
    sub.p256dh = keys.get("p256dh")
    sub.auth = keys.get("auth")
    db.session.commit()
    return jsonify({"ok": True})


@push_bp.route("/test", methods=["POST"])
@login_required
def test_push():
    from app.push_utils import enviar_push_a_usuario
    n = enviar_push_a_usuario(current_user.user_id, "Sistema de Facturación",
                              "Notificación de prueba ✅")
    return jsonify({"ok": True, "enviados": n})
