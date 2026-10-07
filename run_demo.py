"""
Arranca el sistema en MODO DEMO: usa la base de datos 'sistema_inventario_huang_demo'
(y los datos ficticios creados con setups_demo.py) y escucha en el puerto 5011,
separado del sistema real (5010).

Uso:
    python run_demo.py
"""
import os

os.environ["DB_NAME"] = "sistema_inventario_huang_demo"
os.environ["PORT"] = "5011"
os.environ["DEMO_MODE"] = "1"

from waitress import serve
from app import create_app

app = create_app()

if __name__ == "__main__":
    print("Modo DEMO en http://127.0.0.1:" + str(app.config["PORT"]))
    print("   Base: " + app.config["DB_NAME"])
    print("   Usuario: demo / demo123")
    serve(app, host="127.0.0.1", port=app.config["PORT"])
