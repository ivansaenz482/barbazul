"""
Crea un usuario desde la linea de comandos (uso interno del instalador).

Uso:
    venv\\Scripts\\python crear_admin.py <usuario> <nombre_completo> <contrasena> [rol]
"""
import sys

import bcrypt

from app import create_app
from app.extensions import db
from app.models import Role, User


def main():
    if len(sys.argv) < 4:
        print("Uso: crear_admin.py <usuario> <nombre_completo> <contrasena> [rol]")
        return 1

    username = sys.argv[1].strip()
    full_name = sys.argv[2].strip()
    password = sys.argv[3]
    role_name = sys.argv[4].strip().lower() if len(sys.argv) > 4 else "administrador"

    app = create_app()
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"El usuario '{username}' ya existe.")
            return 0

        role = Role.query.filter_by(role_name=role_name).first()
        if not role:
            print(f"El rol '{role_name}' no existe. Usa: administrador, personal")
            return 1

        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        new_user = User(
            username=username,
            password_hash=password_hash,
            full_name=full_name,
            role_id=role.role_id,
            active=True,
        )
        db.session.add(new_user)
        db.session.commit()
        print(f"Usuario '{username}' creado con rol '{role_name}'.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
