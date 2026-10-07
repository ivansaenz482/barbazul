"""
Respaldo automatico de la base de datos usando mysqldump (incluido con MySQL Server).

No requiere ninguna libreria de Python nueva. Solo necesita que "mysqldump" este
disponible: normalmente ya esta en el PATH de Windows despues de instalar MySQL,
o se puede indicar su ruta exacta con MYSQLDUMP_PATH en el archivo .env.
"""
import os
import subprocess
from datetime import datetime

from flask import current_app


class BackupError(Exception):
    pass


def _backup_folder():
    folder = current_app.config["BACKUP_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    return folder


def create_backup():
    """
    Genera un archivo .sql con una copia completa de la base de datos.
    Devuelve una tupla (exito: bool, mensaje: str, filepath: str|None)
    """
    mysqldump_cmd = current_app.config.get("MYSQLDUMP_PATH", "").strip() or "mysqldump"

    db_host = current_app.config["DB_HOST"]
    db_port = current_app.config["DB_PORT"]
    db_user = current_app.config["DB_USER"]
    db_password = current_app.config["DB_PASSWORD"]
    db_name = current_app.config["DB_NAME"]

    folder = _backup_folder()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{db_name}_{timestamp}.sql"
    filepath = os.path.join(folder, filename)

    comando = [
        mysqldump_cmd,
        "-h", db_host,
        "-P", str(db_port),
        "-u", db_user,
        "--routines", "--events", "--single-transaction",
        db_name,
    ]

    # La contraseña se pasa por variable de entorno, no como argumento,
    # para que no quede visible en el listado de procesos de Windows.
    env = os.environ.copy()
    if db_password:
        env["MYSQL_PWD"] = db_password

    try:
        with open(filepath, "wb") as out_file:
            resultado = subprocess.run(
                comando, stdout=out_file, stderr=subprocess.PIPE, env=env, timeout=120
            )

        if resultado.returncode != 0:
            error_detalle = resultado.stderr.decode(errors="ignore").strip()
            if os.path.exists(filepath):
                os.remove(filepath)
            return False, f"mysqldump devolvió un error: {error_detalle}", None

        if os.path.getsize(filepath) == 0:
            os.remove(filepath)
            return False, "El respaldo se generó vacío. Revisa las credenciales de la base de datos.", None

        _rotar_backups_antiguos(folder)
        return True, f"Respaldo creado correctamente: {filename}", filepath

    except FileNotFoundError:
        if os.path.exists(filepath):
            os.remove(filepath)
        return False, (
            "No se encontró 'mysqldump'. Verifica que MySQL esté instalado, o configura "
            "MYSQLDUMP_PATH en tu archivo .env con la ruta completa a mysqldump.exe "
            "(normalmente en 'C:\\Program Files\\MySQL\\MySQL Server 8.0\\bin\\mysqldump.exe')."
        ), None
    except subprocess.TimeoutExpired:
        if os.path.exists(filepath):
            os.remove(filepath)
        return False, "El respaldo tardó demasiado y se canceló (más de 2 minutos).", None
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return False, f"No se pudo generar el respaldo: {e}", None


def _rotar_backups_antiguos(folder):
    """Mantiene solo los ultimos N respaldos, para no llenar el disco poco a poco"""
    max_backups = int(current_app.config.get("MAX_BACKUPS", 30))
    archivos = list_backups(folder)
    if len(archivos) > max_backups:
        for archivo in archivos[max_backups:]:
            try:
                os.remove(archivo["filepath"])
            except OSError:
                pass


def list_backups(folder=None):
    """Lista los respaldos existentes, mas reciente primero"""
    folder = folder or _backup_folder()
    if not os.path.isdir(folder):
        return []

    archivos = []
    for nombre in os.listdir(folder):
        if not nombre.endswith(".sql"):
            continue
        ruta = os.path.join(folder, nombre)
        archivos.append({
            "filename": nombre,
            "filepath": ruta,
            "size_kb": round(os.path.getsize(ruta) / 1024, 1),
            "fecha": datetime.fromtimestamp(os.path.getmtime(ruta)),
        })

    archivos.sort(key=lambda a: a["fecha"], reverse=True)
    return archivos
