"""
Punto de entrada para uso NORMAL (una computadora / misma PC).

Usa Waitress (servidor de producción) y escucha solo en 127.0.0.1.
Un solo proceso, sin recargador de debug, por lo que el sistema puede
detenerse limpiamente con "Detener_Sistema.vbs".

El puerto se define en .env (PORT=5010).

Este archivo lo usa "Iniciar_Sistema.vbs" (sin ventanas).
"""
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from waitress import serve
from app import create_app

app = create_app()

if __name__ == "__main__":
    serve(app, host="127.0.0.1", port=app.config["PORT"])