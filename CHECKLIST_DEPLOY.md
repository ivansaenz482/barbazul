# Checklist de despliegue — Sistema Barbazul (Railway)

Marca cada punto en orden. Si algo falla, mira la sección **Solución de problemas**.

---

## ANTES de subir
- [ ] `.env` **no** está en Git (está en `.gitignore`).
- [ ] `datos_iniciales.sql` lo tienes a mano en tu PC (no va al repo).
- [ ] El repo de GitHub es **privado**.
- [ ] Archivos presentes: `wsgi.py`, `Procfile`, `railway.json`, `requirements.txt`, `.python-version`, `nixpacks.toml`.

## CONFIGURAR en Railway
- [ ] Proyecto creado desde el repo de GitHub.
- [ ] Servicio **MySQL** agregado.
- [ ] Variables en el **servicio web**:
  - [ ] `DATABASE_URL` = `${{ MySQL.MYSQL_PRIVATE_URL }}`
  - [ ] `SECRET_KEY` = clave larga y aleatoria
  - [ ] `BEHIND_PROXY` = `1`
  - [ ] (opcional) `SMTP_*` para alertas por correo
- [ ] Deploy termina en **Success**.
- [ ] **Domain** generado (Settings → Networking → Generate Domain).

## IMPORTAR datos (una sola vez)
- [ ] Activaste **TCP Proxy** en el servicio MySQL (Settings → Networking).
- [ ] Copiaste host/puerto/usuarios/clave públicos.
- [ ] Importaste el respaldo:
  ```powershell
  cmd /c '"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -h HOST -P PUERTO -u root -p BASE < datos_iniciales.sql'
  ```
- [ ] No dio errores ("Query OK" / sin mensajes de error).

## PROBAR la aplicación (por la URL HTTPS)
- [ ] Abre el login sin errores (no muestra "Error interno").
- [ ] Entra con tu usuario **`admin`** y su contraseña.
- [ ] **Dashboard** carga (menú lateral visible).
- [ ] **Productos / Stock** muestra tus productos con su stock.
- [ ] **Ventas / Pedidos** muestra ventas históricas.
- [ ] **Clientes** y **Vendedores** con datos.
- [ ] **Reportes → Ganancias** calcula (ventas − costo − gastos).
- [ ] **Gastos** y **RRHH** cargan.
- [ ] Crear una **venta de prueba** funciona (descuenta stock).
- [ ] **Logo/Configuración**: el logo se ve (si lo tenías).

## IMÁGENES y OCR
- [ ] El **logo del negocio** aparece en la cabecera/menú.
- [ ] Una imagen de **producto** se ve en la lista.
- [ ] **Compras → Nueva**: subir una foto/PDF de factura y el OCR extrae texto.
      (Si falla el OCR, revisa que `nixpacks.toml` esté incluido.)
- [ ] Al **convertir un pedido a proveedor en Compra**, se puede adjuntar la imagen
      y se muestra en el detalle de la compra.

## PERSISTENCIA (importante)
- [ ] Creaste un **Volume** montado en **`/app/uploads`** en el servicio web
      (para que logo e imágenes NO se borren al redeploy).

## SEGURIDAD
- [ ] `SECRET_KEY` distinta a la de desarrollo.
- [ ] Contraseña de MySQL robusta.
- [ ] HTTPS activo (Railway lo da; dominio propio con Custom Domain).
- [ ] Creados los **usuarios** del negocio en Administración → Usuarios y permisos,
      cada uno con su rol y permisos.

## RESPALDOS
- [ ] Tienes una copia local de `datos_iniciales.sql`.
- [ ] Definiste cómo respaldar (Railway Backup / `python backup_db.py` / cron).

---

## Solución de problemas

**"Application failed to respond" / 502**
- Revisa **Deploy logs**. Normalmente es la base de datos:
  - Que `DATABASE_URL` esté bien (usa la **privada** interna).
  - Que importaste los datos (si la base está vacía, el login no encuentra usuarios).

**Login dice usuario/contraseña incorrectos**
- No se importaron los datos, o importaste en la base equivocada.
- Verifica que la base (`MYSQLDATABASE`, suele ser `railway`) tenga la tabla `users`
  con el usuario `admin`.

**Las imágenes/logo desaparecen tras un redeploy**
- Falta el **Volume** en `/app/uploads` (ver sección Persistencia).

**El OCR no lee las facturas**
- Asegura que `nixpacks.toml` está en el repo (instala `tesseract-ocr`).
- Revisa los logs del deploy para confirmar que se instaló.

**Redirect raro / links con http en vez de https**
- Confirma `BEHIND_PROXY=1` en las variables.

**Cambiar el dominio**
- Settings → Networking → **Custom Domain** → agrega tu dominio y el CNAME.
