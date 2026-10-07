"""
Punto de entrada para USO EN RED (varias computadoras del mismo local).

Diferencias con run.py:
- run.py           -> servidor de pruebas, solo funciona bien para 1 persona a la vez,
                       y solo se puede abrir desde la MISMA computadora (127.0.0.1).
- run_produccion.py -> servidor robusto (Waitress), soporta varios usuarios conectados
                        al mismo tiempo, y escucha en toda la red local (0.0.0.0),
                        para que otras computadoras del local puedan entrar por su navegador.

Uso:
    python run_produccion.py

Luego, en las OTRAS computadoras del mismo local (conectadas a la misma WiFi/cable),
abre el navegador y entra a:
    http://IP_DE_ESTA_COMPUTADORA:5010

Para saber la IP de esta computadora, corre en su propia terminal:
    ipconfig
y busca "Dirección IPv4" (ejemplo: 192.168.1.50).

El puerto se define en .env (PORT=5010). IMPORTANTE: esta computadora debe permanecer
encendida y con este programa corriendo mientras las demás lo usan.
Ver README.md, sección "Uso en red local (varias computadoras)".
"""
from waitress import serve
from app import create_app

app = create_app()

if __name__ == "__main__":
    port = app.config["PORT"]
    print("=" * 60)
    print("Servidor de Sistema de Inventario iniciado")
    print("Accesible desde esta misma computadora en:")
    print(f"    http://127.0.0.1:{port}")
    print("Accesible desde OTRAS computadoras de esta red en:")
    print(f"    http://<IP-de-esta-computadora>:{port}")
    print('(Corre "ipconfig" en otra terminal para ver esa IP)')
    print("=" * 60)
    serve(app, host="0.0.0.0", port=port)