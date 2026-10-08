import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuracion base leida desde variables de entorno (.env)"""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-cambiar")

    # Puerto del servidor web (se cambio de 5000 a 5010 para no chocar con el
    # sistema de la copia. Se puede cambiar desde .env -> PORT)
    PORT = int(os.getenv("PORT", "5010"))

    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "sistema_inventario_huang")

    # Si existe DATABASE_URL (Railway, Render, Aiven, PlanetScale...) se usa esa.
    # Si no, se arma la cadena con las variables DB_* de arriba.
    _database_url = os.getenv("DATABASE_URL", "").strip()
    if _database_url:
        if _database_url.startswith("mysql://"):
            _database_url = _database_url.replace("mysql://", "mysql+pymysql://", 1)
        SQLALCHEMY_DATABASE_URI = _database_url
    else:
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Poner en 1 cuando el sistema corre detras de un proxy con HTTPS (Nginx/Railway).
    BEHIND_PROXY = os.getenv("BEHIND_PROXY", "0") == "1"

    # Zona horaria del negocio (horas respecto a UTC). Ecuador = -5 (sin horario de verano).
    TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "-5"))

    # Notificaciones push (Web Push / VAPID). Se pueden sobreescribir por .env.
    VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY",
                                 "BJdJrzsAp3V4gsj-gkgaGVtJdUqYrfE88IMDOvU8h1GM9UGkyzH9sI4oXv0BC8Fteu68Ed64kEWANA6B86RIZxY")
    VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY",
                                  "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgZrKqZf8e_RwyghpZYtp6qplvo1EpGHPpxVFfFm-JSDahRANCAASXSa87AKd1eILI_oJIGhlbSXVKmK3xPPCDAzr1PIdRjPVBpMsx_bCOKF79AQvBbXruvBHeuJBFgDQOgfOkSGcW")
    VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@barbazul.local")

    # Carpeta donde se guardan las facturas (PDF/imagen) subidas
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads", "facturas")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max por archivo
    ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

    # Ruta al ejecutable de Tesseract OCR (opcional, solo si no esta en el PATH del sistema)
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()

    # Correo de alertas (opcional). Si se deja vacio, el sistema simplemente no envia correos.
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = os.getenv("SMTP_PORT", "587")
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")

    # Respaldo automatico de la base de datos
    BACKUP_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backups")
    MYSQLDUMP_PATH = os.getenv("MYSQLDUMP_PATH", "").strip()
    MAX_BACKUPS = os.getenv("MAX_BACKUPS", "30")

    # Entorno de DEMO (pruebas). Si es "1", muestra un aviso claro de que es
    # un entorno de pruebas y NO el sistema real del negocio.
    DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"

    # Fotos de perfil de usuario
    AVATAR_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads", "avatars")
    ALLOWED_AVATAR_EXTENSIONS = {"png", "jpg", "jpeg"}

    # Imagenes de productos
    PRODUCT_IMAGE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads", "productos")
    ALLOWED_PRODUCT_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

    # Logo del negocio (aparece en facturas/notas de venta y en el menu)
    LOGO_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads", "logo")
    ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

    # Certificado digital del SRI (.p12/.pfx) y XML de comprobantes
    SRI_CERT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads", "sri")
