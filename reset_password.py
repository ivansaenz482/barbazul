"""
Resetea la contrasena de un usuario usando bcrypt.
Uso: python reset_password.py [usuario] [nueva_clave]
Por defecto: admin / NovaSys2026
Para la nube: define DATABASE_URL antes de ejecutarlo.
"""
import sys
import bcrypt
from app import create_app
from app.extensions import db
from app.models import User

username = sys.argv[1] if len(sys.argv) > 1 else "admin"
nueva = sys.argv[2] if len(sys.argv) > 2 else "NovaSys2026"

app = create_app()
with app.app_context():
    print("Base: " + app.config["DB_NAME"])
    u = User.query.filter_by(username=username).first()
    if not u:
        print(f"ERROR: no existe el usuario '{username}'.")
        sys.exit(1)
    u.password_hash = bcrypt.hashpw(nueva.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.session.commit()
    print(f"OK: contrasena de '{username}' actualizada.")
