# Sistema de Inventario — Backend

Proyecto Flask conectado a MySQL local (`sistema_inventario_huang`). Corre 100% en tu computadora, sin nube.

## 1. Requisitos previos
- Python 3.10+ instalado
- MySQL Server corriendo localmente (ya lo tienes)
- La base de datos se crea automáticamente al ejecutar `python init_db.py` (o con el instalador `instalar.ps1`)

## 2. Instalación (primera vez)

Abre esta carpeta en VS Code, luego en la terminal integrada:

```bash
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# En Windows:
venv\Scripts\activate
# En Mac/Linux:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

## 3. Configurar tu contraseña de MySQL

1. Copia el archivo `.env.example` y renómbralo a `.env`
2. Abre `.env` y reemplaza `DB_PASSWORD` con tu contraseña real de MySQL root

## 4. Ejecutar el servidor

```bash
python run.py
```

Deberías ver algo como:
```
* Running on http://127.0.0.1:5010
```

## 5. Verificar que todo conecta bien

Abre tu navegador en:
- http://127.0.0.1:5010/  → debe mostrar el mensaje de bienvenida
- http://127.0.0.1:5010/test-db  → debe mostrar un JSON confirmando la conexión a MySQL, con el conteo de productos, clientes y los roles configurados (administrador, personal)

Si ves `"estado": "conexion exitosa"`, ¡todo está funcionando! 🎉

Si ves un error, generalmente es:
- Contraseña incorrecta en `.env`
- MySQL Server no está corriendo (revisa `services.msc`)
- El nombre de la base de datos no coincide (`DB_NAME` en `.env` debe ser `sistema_inventario_huang`)

## Estructura del proyecto

```
proyecto_inventario/
├── app/
│   ├── __init__.py        # Application factory
│   ├── config.py          # Configuracion (lee .env)
│   ├── extensions.py      # db, login_manager compartidos
│   ├── models/
│   │   └── core.py         # Modelos: Role, User, Product, Customer, etc.
│   └── routes/
│       └── main.py         # Rutas (endpoints)
├── uploads/facturas/       # Aqui se guardaran las facturas PDF/imagen
├── .env.example
├── .gitignore
├── requirements.txt
└── run.py                  # Punto de entrada
```

## Uso en red local (varias computadoras del mismo local)

Si quieres que varias computadoras del mismo local (mismo WiFi o cable de red) usen el
sistema al mismo tiempo, **no necesitas instalar nada en esas otras computadoras** —
solo necesitan un navegador. Todo corre desde UNA computadora "servidor".

### 1. Elige la computadora servidor
Debe ser la que se queda encendida durante el horario de trabajo (por ejemplo, la de
la oficina o la caja principal). Ahí es donde ya tienes instalado MySQL y el proyecto.

### 2. Averigua la IP local de esa computadora
En su terminal:
```powershell
ipconfig
```
Busca la línea **"Dirección IPv4"** dentro de tu adaptador de red (WiFi o Ethernet).
Se ve algo como `192.168.1.50`. Anótala.

### 3. Abre el puerto 5010 en el Firewall de Windows
En la computadora servidor, abre PowerShell **como Administrador** (clic derecho →
"Ejecutar como administrador") y corre:
```powershell
New-NetFirewallRule -DisplayName "Sistema Inventario" -Direction Inbound -LocalPort 5010 -Protocol TCP -Action Allow
```
Esto permite que otras computadoras de la red le hablen a este programa. MySQL no
necesita ningún cambio ni puerto abierto — solo esta computadora habla con MySQL.

### 4. Inicia el servidor con Waitress (no con `run.py`)
```powershell
python run_produccion.py
```
Este programa **debe quedar corriendo** mientras las demás computadoras lo usan. Puedes
minimizar la ventana, pero no cerrarla.

### 5. En las OTRAS computadoras del local
Abre Chrome/Edge y entra a:
```
http://192.168.1.50:5010
```
(cambia `192.168.1.50` por la IP real que anotaste en el paso 2)

Ahí verán la misma pantalla de inicio de sesión, y cada quien entra con su propio
usuario (administrador o personal) — todos comparten la misma base de datos en tiempo real.

### Notas importantes
- Si la computadora servidor se apaga o se desconecta de la red, las demás pierden acceso.
- La IP local puede cambiar si el router se reinicia. Si eso pasa seguido, puedes configurar
  una "IP fija" para esa computadora en el router (pregúntame si necesitas ayuda con esto).
- Cuando el sistema quede definitivo, conviene configurar esta computadora para que
  `run_produccion.py` se inicie automáticamente al prender Windows (con el Programador
  de Tareas, similar a como configuramos las alertas por correo).

## Respaldo automático (opcional pero muy recomendado)

El sistema puede generar copias de seguridad de tu base de datos completa (`sistema_inventario_huang`)
de forma automática, sin depender de la nube — los respaldos quedan guardados en la carpeta
`backups/` de este proyecto, en tu propia computadora.

### 1. Pruébalo manualmente primero
```powershell
python backup_db.py
```
Deberías ver un mensaje confirmando que se creó el archivo (o explicando qué falta, por ejemplo
si `mysqldump` no está en el PATH — en ese caso, agrega `MYSQLDUMP_PATH` a tu `.env` con la ruta
completa, normalmente `C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe`).

### 2. Revísalo desde la app
Entra al menú **"Respaldos"** (solo visible para el administrador) para ver el historial,
descargar cualquier respaldo, generar uno nuevo con un clic, o eliminar los que ya no necesites.

### 3. Prográmalo con el Programador de Tareas de Windows
Sigue los mismos pasos que usamos para las alertas por correo (sección siguiente), pero esta vez:
- Nombre: `Respaldo Sistema Inventario`
- Frecuencia: **Diariamente**, a una hora de bajo uso (ej. 2:00 AM)
- Programa: la ruta a tu Python del entorno virtual (`...\venv\Scripts\python.exe`)
- Argumentos: `backup_db.py`
- Iniciar en: la carpeta del proyecto

### 4. Guarda copias también fuera de la computadora (recomendado)
Los respaldos automáticos te protegen de errores humanos (borrar algo sin querer) o fallos de la
base de datos, pero **no** te protegen si la computadora se daña o se pierde. Cada cierto tiempo,
copia manualmente la carpeta `backups/` a un disco externo o USB — así quedas cubierto ante
cualquier escenario, sin necesidad de subir nada a la nube.

## Notificaciones automáticas (opcional)

El sistema puede enviarte un correo-resumen de alertas (bajo stock, sobre stock, créditos vencidos)
de forma automática, sin necesidad de tener la aplicación abierta.

### 1. Configura el correo en tu archivo `.env`
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tucorreo@gmail.com
SMTP_PASSWORD=una_clave_de_aplicacion_de_gmail
ALERT_EMAIL_TO=correo_donde_quieres_recibir_las_alertas@gmail.com
```
Si usas Gmail, no pongas tu contraseña normal — genera una "contraseña de aplicación" en
`https://myaccount.google.com/apppasswords` (requiere tener activada la verificación en 2 pasos).

### 2. Pruébalo manualmente primero
```powershell
python send_alerts.py
```
Deberías ver un mensaje confirmando el envío (o explicando qué falta configurar).

### 3. Prográmalo con el Programador de Tareas de Windows
1. Abre el **Programador de tareas** (búscalo en el menú de inicio de Windows)
2. Clic en **"Crear tarea básica..."**
3. Nombre: `Alertas Sistema Inventario` → Siguiente
4. Frecuencia: **Diariamente** → elige la hora (ej. 8:00 AM) → Siguiente
5. Acción: **"Iniciar un programa"** → Siguiente
6. En "Programa o script", pon la ruta completa a tu Python **dentro del entorno virtual**, por ejemplo:
   ```
   C:\Users\tu_usuario\Downloads\proyecto_inventario\proyecto_inventario\venv\Scripts\python.exe
   ```
7. En "Agregar argumentos", pon:
   ```
   send_alerts.py
   ```
8. En "Iniciar en", pon la ruta de la carpeta del proyecto (sin el `\venv\...`):
   ```
   C:\Users\tu_usuario\Downloads\proyecto_inventario\proyecto_inventario
   ```
9. Finalizar

A partir de ahí, todos los días a la hora que elegiste, Windows va a revisar las alertas y enviarte el correo automáticamente — sin depender de ningún servicio en la nube.



Una vez confirmes que `/test-db` funciona, seguimos con el módulo de **login** (administrador / personal) o el **CRUD de productos** — lo que prefieras.
