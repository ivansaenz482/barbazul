from functools import wraps
import os
from datetime import datetime, timezone, timedelta
from flask import abort
from flask_login import current_user
import barcode
from barcode.writer import SVGWriter


def ahora_local():
    """Hora actual en la zona horaria del negocio (Ecuador = UTC-5 por defecto)."""
    try:
        from flask import current_app
        offset = int(current_app.config.get("TIMEZONE_OFFSET", -5))
    except Exception:
        offset = -5
    return datetime.now(timezone(timedelta(hours=offset)))


def hora_local():
    """Hora (time) actual local, sin zona ni microsegundos, para guardar en la BD."""
    return ahora_local().time().replace(microsecond=0, tzinfo=None)


def fecha_local():
    """Fecha (date) actual local del negocio."""
    return ahora_local().date()


def resolver_ruta_upload(ruta_guardada, carpeta_actual):
    """
    Devuelve la ruta real de un archivo subido.
    Si la ruta guardada ya no existe (por ejemplo, al copiar el proyecto a otra
    computadora), busca el archivo por su nombre dentro de la carpeta actual.
    Devuelve None si no se encuentra.
    """
    if not ruta_guardada:
        return None
    if os.path.isfile(ruta_guardada):
        return ruta_guardada
    if carpeta_actual:
        candidato = os.path.join(carpeta_actual, os.path.basename(ruta_guardada))
        if os.path.isfile(candidato):
            return candidato
    return None


def role_required(*allowed_roles):
    """
    Uso:
        @role_required("administrador")
        def vista_solo_admin(): ...

        @role_required("administrador", "personal")
        def vista_para_ambos(): ...
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role.role_name not in allowed_roles:
                abort(403)  # Prohibido: no tiene el rol necesario
            return f(*args, **kwargs)
        return wrapped
    return decorator


def perm_required(perm_check):
    """
    Verifica un permiso granular del usuario.
    - Si es administrador, siempre permite.
    - Si perm_check es un string, lo interpreta como atributo/método del User
      (ej. "can_view_inventario", "can_edit_stock", "perm_inventario").
    - Si es callable, lo ejecuta con el usuario.

    Uso:
        @perm_required("can_view_inventario")
        @perm_required("can_edit_stock")
        @perm_required("can_view_reporte_caja")
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.is_admin():
                return f(*args, **kwargs)
            # perm_check puede ser el nombre de un método/attr del User
            if isinstance(perm_check, str):
                attr = getattr(current_user, perm_check, None)
                if callable(attr):
                    if attr():
                        return f(*args, **kwargs)
                elif attr:
                    return f(*args, **kwargs)
            elif callable(perm_check):
                if perm_check(current_user):
                    return f(*args, **kwargs)
            abort(403)
        return wrapped
    return decorator


def _digito_control_ean13(codigo12):
    """Calcula el digito de control de un codigo EAN-13 (primeros 12 digitos)."""
    total = sum((3 if i % 2 == 0 else 1) * int(c) for i, c in enumerate(codigo12))
    return (10 - total % 10) % 10


def generar_ean13(base):
    """
    Genera un codigo EAN-13 unico y valido a partir de un numero base.
    Usa el prefijo 786 (Ecuador) + 9 digitos del numero, y calcula el digito de control.
    Ej: base=15 -> '786000000015' + digito control.
    """
    prefijo = "786"
    cuerpo = str(int(base) % 1000000000).zfill(9)
    codigo12 = prefijo + cuerpo
    return codigo12 + str(_digito_control_ean13(codigo12))


def generar_barcode_svg(codigo, incluir_texto=True, alto=12):
    """
    Genera la imagen SVG de un codigo de barras.
    Usa EAN-13 si el codigo tiene 13 digitos validos; en caso contrario usa Code 128.
    Devuelve el SVG como string (listo para embeder con |safe) o None si no se puede.
    """
    codigo = str(codigo or "").strip()
    if not codigo:
        return None
    opciones = {"write_text": incluir_texto, "module_width": 0.22, "module_height": alto}
    if len(codigo) == 13 and codigo.isdigit():
        try:
            svg = barcode.get("ean13", codigo, writer=SVGWriter()).render(opciones)
            return svg.decode("utf-8")
        except Exception:
            pass
    try:
        svg = barcode.get("code128", codigo, writer=SVGWriter()).render(opciones)
        return svg.decode("utf-8")
    except Exception:
        return None

