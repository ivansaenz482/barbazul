"""
Script para crear el primer usuario administrador.
Ejecutar UNA sola vez (o cada vez que necesites crear un usuario nuevo):

    python create_user.py

Sigue las instrucciones en pantalla.
"""
import bcrypt
from getpass import getpass
from app import create_app
from app.extensions import db
from app.models import User, Role

app = create_app()

with app.app_context():
    print("=== Crear nuevo usuario ===")
    username = input("Nombre de usuario: ").strip()

    if User.query.filter_by(username=username).first():
        print(f"❌ El usuario '{username}' ya existe.")
        exit()

    full_name = input("Nombre completo: ").strip()
    email = input("Correo (opcional): ").strip()
    phone = input("Teléfono (opcional): ").strip()

    password = getpass("Contraseña: ")
    password_confirm = getpass("Confirma la contraseña: ")

    if password != password_confirm:
        print("❌ Las contraseñas no coinciden.")
        exit()

    print("\nRoles disponibles: administrador, personal")
    role_name = input("Rol (administrador/personal): ").strip().lower()

    role = Role.query.filter_by(role_name=role_name).first()
    if not role:
        print(f"❌ El rol '{role_name}' no existe.")
        exit()

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    new_user = User(
        username=username,
        password_hash=password_hash,
        full_name=full_name,
        email=email or None,
        phone=phone or None,
        role_id=role.role_id,
        active=True
    )

    db.session.add(new_user)
    db.session.commit()

    print(f"\n✅ Usuario '{username}' creado correctamente con rol '{role_name}'.")
