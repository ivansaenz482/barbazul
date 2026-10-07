"""
Punto de entrada WSGI para PRODUCCION (Gunicorn, Railway, Render...).

No ejecutes este archivo con 'python wsgi.py'; lo usan los servidores de
produccion. Por ejemplo, con Gunicorn:

    gunicorn wsgi:app --bind 0.0.0.0:$PORT
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Permite probarlo localmente: python wsgi.py
    import os
    port = int(os.getenv("PORT", "5010"))
    app.run(host="0.0.0.0", port=port)
