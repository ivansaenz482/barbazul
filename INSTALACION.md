# Guía de Instalación — Sistema de Facturación Barbazul

Pasos para instalar el sistema en una computadora nueva (desde cero).

---

## 0. Método rápido: instalador de un solo botón (recomendado)

1. Copia la carpeta completa del proyecto a la computadora nueva.
2. Borra la carpeta `venv` que venga dentro (si existe).
3. Entra a la carpeta y haz doble clic en **`Instalar_Sistema.bat`**.
4. Acepta la ventana de permisos de administrador.
5. Responde las preguntas:
   - **Contraseña de MySQL** (la de root; si MySQL ya estaba instalado).
   - Si MySQL **no** está instalado, se abrirá el asistente de MySQL:
     elige *Developer Default*, pulsa **Execute** y define una contraseña para `root`
     (anótala). Al terminar, el asistente continúa solo.
   - **Usuario y contraseña del administrador** del sistema (solo si la base es nueva).
6. Al final deja dos iconos en el Escritorio:
   - `Sistema de Facturacion Barbazul` → abre el sistema (sin ventanas).
   - `Detener Sistema Barbazul` → lo cierra.

> El instalador instala Python y MySQL automáticamente si faltan, crea la base de
> datos `sistema_inventario_huang`, instala las dependencias, crea el usuario
> administrador y los accesos directos. Puedes ejecutarlo varias veces: solo hace
> lo que falta.

> También existe el manual en Word: **`MANUAL_DE_INSTALACION.docx`**.

---

## 0.1 Instalar EN OTRA PC CON LOS DATOS ACTUALES (migración)

Si quieres que la computadora nueva tenga **exactamente los mismos datos**
(productos, clientes, ventas, usuarios, logo, etc.) que esta PC:

1. En **esta** computadora, genera/actualiza el respaldo de datos:
   ```bat
   venv\Scripts\python backup_db.py
   ```
2. Copia el último archivo generado en `backups\` y renómbralo como
   **`datos_iniciales.sql`** en la **raíz** del proyecto
   (si ya existe uno, reemplázalo por el más reciente).
3. Copia **toda la carpeta del proyecto** a la computadora nueva
   (incluyendo `datos_iniciales.sql` y la carpeta `uploads\` con el logo e imágenes).
4. Borra la carpeta `venv` de la copia y ejecuta **`Instalar_Sistema.bat`**.

El instalador detecta `datos_iniciales.sql` y lo importa automáticamente: la base
queda con toda la información y **no** pide crear un usuario nuevo (se usan los
usuarios que ya vienen en los datos). El logo y las imágenes se muestran igual
aunque cambie la letra o ruta de la carpeta.

> ¿Y si **no** quieres los datos actuales? Simplemente **no** copies
> `datos_iniciales.sql`: el instalador creará una base nueva vacía y te pedirá
> el usuario administrador.

---

## 1. Método manual

### 1.1 Instalar Python

1. Descarga Python 3.11, 3.12 o 3.13 desde https://www.python.org/downloads/
2. Al instalar, **marca la casilla** "Add python.exe to PATH".
3. Verifica en una terminal: `python --version`

### 1.2 Instalar MySQL (Workbench)

1. Instala **MySQL Server 8** (se instala junto con MySQL Workbench).
2. Anota el usuario y la contraseña que configures (normalmente `root`).
3. Asegúrate de que el **servicio MySQL esté corriendo** (Services → MySQL80 → Iniciar).
4. Crea la base de datos en Workbench:

```sql
CREATE DATABASE sistema_inventario_huang CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

5. Importa los datos existentes (si los hay) con **Server → Data Import**, o importa
   el archivo `.sql` más reciente que encuentres dentro de la carpeta `backups/`.

> El sistema NO crea las tablas solo: la base debe existir en MySQL antes de iniciar.

### 1.3 Copiar el proyecto

1. Copia la carpeta completa del proyecto a la computadora nueva
   (por ejemplo a `C:\SistemaBarbazul`).
2. Abre la carpeta y entra a la subcarpeta `venv` → **bórrala** (se recrea en el paso 5).

### 1.4 Configurar la conexión a la base de datos

1. En la carpeta del proyecto, copia el archivo `.env.example` y renómbralo a `.env`.
2. Edítalo y coloca tus datos reales de MySQL:

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=tu_contraseña_de_mysql
DB_NAME=sistema_inventario_huang
```

3. Guarda el archivo.

### 1.5 Crear el entorno virtual e instalar dependencias

Abre una terminal dentro de la carpeta del proyecto y ejecuta:

```bat
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

> Si `PyMuPDF` falla por "Unable to find Visual Studio", no te preocupes:
> edita `requirements.txt`, quita esa línea y vuelve a correr el comando.
> Solo afecta a PDFs escaneados; las fotos y PDFs normales siguen funcionando.

### 1.6 Crear el usuario administrador

```bat
venv\Scripts\python create_user.py
```

Sigue las instrucciones en pantalla (usuario, nombre completo, contraseña, rol `administrador`).

### 1.7 Iniciar el sistema

| Forma | Cómo | Ventana negra |
|---|---|---|
| **Normal (sin ventanas)** | Doble clic en `Iniciar_Sistema.vbs` | No aparece |
| Con ventana (para revisar errores) | Doble clic en `Iniciar_Sistema.bat` | Aparece |

El sistema abre el navegador automáticamente en `http://127.0.0.1:5010`.

Para detenerlo: doble clic en `Detener_Sistema.vbs` (o, en el modo con ventana,
presiona `Ctrl + C` en la ventana negra).

### 1.8 Acceso directo en el Escritorio (opcional)

1. Clic derecho en el Escritorio → **Nuevo → Acceso directo**.
2. Ubicación: `C:\SistemaBarbazul\Iniciar_Sistema.vbs` (ajusta la ruta).
3. Ponle nombre, por ejemplo "Sistema de Facturación BARBAZUL".

Repite el mismo paso con `Detener_Sistema.vbs` si quieres un acceso para detener.

---

## Respaldo de la base de datos

El sistema incluye un respaldo automático manual:

```bat
venv\Scripts\python backup_db.py
```

Los respaldos se guardan en la carpeta `backups/` como archivos `.sql`.
También puedes programar este script con el **Programador de tareas de Windows**.

## Solución de problemas

- **No abre / dice "No se puede conectar"**: revisa que MySQL esté corriendo y que
  el servicio exista. Abre el archivo `server.log` para ver el error exacto.
- **Error de conexión a base de datos**: revisa que el `.env` tenga la contraseña
  correcta y que la base `sistema_inventario_huang` exista.
- **Puerto 5010 ocupado**: corre `Detener_Sistema.vbs` y vuelve a iniciar.
