"""Helper para registrar acciones en el log de auditoría."""
from flask import request
from flask_login import current_user


def registrar(accion, detalle=None, entidad=None, entidad_id=None):
    """
    Guarda una accion en el log de auditoria y hace commit.
    Se llama DESPUES del commit principal de la operacion.
    No rompe la app si algo falla.
    """
    try:
        from app.extensions import db
        from app.models import AuditLog
        uid = current_user.user_id if current_user.is_authenticated else None
        uname = current_user.username if current_user.is_authenticated else None
        ip = request.remote_addr if request else None
        db.session.add(AuditLog(
            user_id=uid, username=uname, accion=accion, entidad=entidad,
            entidad_id=str(entidad_id) if entidad_id is not None else None,
            detalle=(detalle[:500] if detalle else None), ip=ip,
        ))
        db.session.commit()
    except Exception:
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass
