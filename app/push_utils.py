"""Envio de notificaciones Web Push (VAPID) a los dispositivos suscritos."""
import json

from flask import current_app


def _enviar(info, titulo, cuerpo, url=None):
    try:
        from pywebpush import webpush, WebPushException  # noqa: F401
    except Exception:
        return False
    data = json.dumps({"title": titulo, "body": cuerpo, "url": url or "/dashboard"})
    try:
        webpush(
            subscription_info=info,
            data=data,
            vapid_private_key=current_app.config.get("VAPID_PRIVATE_KEY"),
            vapid_claims={"sub": current_app.config.get("VAPID_SUBJECT", "mailto:admin@example.com")},
        )
        return True
    except Exception:
        return False


def enviar_push(suscripciones, titulo, cuerpo, url=None):
    enviados = 0
    for s in suscripciones:
        if _enviar(s.info(), titulo, cuerpo, url):
            enviados += 1
    return enviados


def enviar_push_a_usuario(user_id, titulo, cuerpo, url=None):
    from app.models import PushSubscription
    return enviar_push(PushSubscription.query.filter_by(user_id=user_id).all(), titulo, cuerpo, url)


def enviar_push_a_todos(titulo, cuerpo, url=None):
    from app.models import PushSubscription
    return enviar_push(PushSubscription.query.all(), titulo, cuerpo, url)
