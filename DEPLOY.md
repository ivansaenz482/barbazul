# Despliegue en la nube — Sistema de Facturación Barbazul

Guía para que el sistema sea accesible **desde cualquier lado** (PC, celular) con
usuarios y permisos. Hay dos caminos: **A) PaaS (fácil)** y **B) VPS (control total)**.

Antes de empezar necesitas:
- Una cuenta en el hosting.
- Tu base de datos exportada: `datos_iniciales.sql` (o un respaldo de `backups/`).
- Un **dominio** (recomendado) para HTTPS.

---

## Opción A — Railway o Render (recomendado para empezar)

1. Sube el proyecto a un repositorio **privado** de GitHub (sin `venv`, sin `.env`).
   El `Procfile` ya está incluido: `web: gunicorn wsgi:app --bind 0.0.0.0:$PORT`.
2. Crea un proyecto en **Railway** (o Render) y conecta el repositorio.
3. Agrega un **servicio MySQL** (Railway: "+ New → Database → MySQL").
4. En las **Variables** del servicio web, copia lo de `.env.produccion`:
   - `DATABASE_URL` = `${{ MySQL.MYSQL_PRIVATE_URL }}` (usa la **privada/interna**;
     ajusta "MySQL" al nombre real de tu servicio de base de datos).
   - `SECRET_KEY` = una clave larga y aleatoria.
   - `BEHIND_PROXY=1`
   - (opcional) las `SMTP_*` para alertas por correo.
5. Deploy. Railway compila e instala `requirements.txt` y arranca con Gunicorn.
6. **Importa tus datos** (una sola vez). Necesitas la URL **PUBLICA**: activa
   **MySQL → Settings → Networking → TCP Proxy**, copia host/puerto/usuario/clave y,
   desde tu PC:
   ```powershell
   cmd /c '"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -h HOST_PUBLICO -P PUERTO_PUBLICO -u root -p BASE < datos_iniciales.sql'
   ```
   (La base suele llamarse `railway`.)
7. Abre la **URL HTTPS** que te da Railway (Settings → Networking → Generate Domain)
   y entra con tu usuario `admin`.

> Render: usa "Web Service" + "MySQL" (o Aiven/PlanetScale) y define las mismas variables.

---

## Opción B — VPS (DigitalOcean / Vultr / Hetzner) con dominio propio

Ejemplo en **Ubuntu 22.04**. Sustituye `tudominio.com` por el tuyo.

### 1) Preparar el servidor
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip mysql-server nginx git
sudo mysql_secure_installation
```

### 2) Subir el código
```bash
sudo mkdir -p /var/www/barbazul && sudo chown $USER /var/www/barbazul
# copia el proyecto a /var/www/barbazul (scp, git clone del repo privado, etc.)
cd /var/www/barbazul
```

### 3) Entorno y dependencias
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4) Base de datos
```bash
sudo mysql -u root -p -e "CREATE DATABASE sistema_inventario_huang CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mysql -u root -p sistema_inventario_huang < datos_iniciales.sql
# Crea un usuario MySQL para la app (mejor que root):
sudo mysql -u root -p -e "CREATE USER 'barbazul'@'localhost' IDENTIFIED BY 'UnaClaveFuerte'; GRANT ALL ON sistema_inventario_huang.* TO 'barbazul'@'localhost'; FLUSH PRIVILEGES;"
```

### 5) Archivo `.env`
```bash
cp .env.produccion .env
nano .env
```
Completa:
```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=barbazul
DB_PASSWORD=UnaClaveFuerte
DB_NAME=sistema_inventario_huang
PORT=8080
BEHIND_PROXY=1
SECRET_KEY=una_clave_larga_y_aleatoria
```

### 6) Servicio systemd (queda corriendo 24/7)
Crea `/etc/systemd/system/barbazul.service`:
```ini
[Unit]
Description=Sistema de Facturacion Barbazul
After=network.target mysql.service

[Service]
User=www-data
WorkingDirectory=/var/www/barbazul
EnvironmentFile=/var/www/barbazul/.env
ExecStart=/var/www/barbazul/venv/bin/gunicorn wsgi:app --bind 127.0.0.1:8080 --workers 3 --threads 4 --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo chown -R www-data:www-data /var/www/barbazul
sudo systemctl daemon-reload
sudo systemctl enable --now barbazul
sudo systemctl status barbazul
```

### 7) Nginx + HTTPS
```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/barbazul
sudo nano /etc/nginx/sites-available/barbazul   # cambia tudominio.com
sudo ln -s /etc/nginx/sites-available/barbazul /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# Tu dominio debe apuntar (DNS tipo A) a la IP del VPS. Luego:
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tudominio.com -d www.tudominio.com
```

Listo: `https://tudominio.com` con HTTPS.

---

## Usuarios y permisos
El sistema ya trae **Administración → Usuarios y permisos**. El administrador crea
cada usuario (vendedor, personal, etc.) con su rol y permisos; cada uno entra desde
el navegador con su usuario y contraseña.

## Respaldos
- **Manual**: `python backup_db.py` (genera `.sql` en `backups/`).
- **Automático**: programa ese comando con `cron` (Linux) o el Programador de
  Tareas (Windows), o usa el respaldo de tu proveedor de base de datos.

## Seguridad (importante)
- Cambia **siempre** la `SECRET_KEY` y la contraseña de MySQL en producción.
- No subas `.env` a Git (ya está en `.gitignore`).
- Usa HTTPS (Certbot/Nginx o el que da el hosting).
- Activa el **firewall** (solo 80/443 abiertos; MySQL solo local).

## Archivos incluidos para despliegue
- `wsgi.py` — punto de entrada para Gunicorn.
- `Procfile` — comando de arranque para Railway/Render.
- `.env.produccion` — variables de entorno de ejemplo.
- `deploy/nginx.conf` — configuración del proxy inverso.
- `requirements.txt` — ya incluye `gunicorn`.
