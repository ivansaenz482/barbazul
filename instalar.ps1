# ============================================================
#  Instalador del Sistema de Facturacion - Barbazul
#  Un solo boton: instala Python y MySQL si faltan, crea la
#  base de datos, el entorno virtual, el usuario administrador
#  y los accesos directos del Escritorio.
#
#  Puedes ejecutarlo varias veces: solo hace lo que falta.
# ============================================================

$ErrorActionPreference = "Stop"
$projDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projDir

function Print-Banner($t) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  $t" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}
function Print-Ok($m) { Write-Host "  [OK] $m" -ForegroundColor Green }
function Print-Step($m) { Write-Host ""; Write-Host ">>> $m" -ForegroundColor Yellow }
function Wait-Press($m) { Read-Host $m | Out-Null }

# Actualiza el PATH de esta sesion (por si se acabo de instalar Python)
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

Print-Banner "Instalador del Sistema de Facturacion - Barbazul"
Write-Host "  Este asistente prepara la computadora para usar el sistema."
Write-Host ""

# ------------------------------------------------------------
# Pedir permisos de administrador (se necesitan para instalar)
# ------------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Solicitando permisos de administrador..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -WorkingDirectory $projDir
    exit 0
}

# ------------------------------------------------------------
# 1/8 - Python
# ------------------------------------------------------------
Print-Step "1/8 - Verificando Python"
$python = $null
$cmdPython = Get-Command python -ErrorAction SilentlyContinue
if ($cmdPython) { $python = $cmdPython.Source }

if (-not $python) {
    Write-Host "Python no esta instalado. Se instalara Python 3.12 (puede tardar unos minutos)..." -ForegroundColor Yellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "No se encontro 'winget' en esta computadora." -ForegroundColor Red
        Write-Host "Instala Python manualmente desde https://www.python.org/downloads/" -ForegroundColor Red
        Write-Host "y marca la casilla 'Add python.exe to PATH'." -ForegroundColor Red
        Wait-Press "Presiona Enter para cerrar"
        exit 1
    }
    & winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements | Out-Host
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python3\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $python = $c; break }
    }
    if (-not $python) { $python = (Get-Command python -ErrorAction SilentlyContinue).Source }
}

if (-not $python) {
    Write-Host "No se pudo instalar Python automaticamente." -ForegroundColor Red
    Write-Host "Descargalo de https://www.python.org/downloads/, marca 'Add to PATH' y vuelve a ejecutar este instalador." -ForegroundColor Red
    Wait-Press "Presiona Enter para cerrar"
    exit 1
}
& $python --version
Print-Ok "Python listo"

# ------------------------------------------------------------
# 2/8 - MySQL
# ------------------------------------------------------------
Print-Step "2/8 - Verificando MySQL"
$mysqlService = @(Get-Service -Name "MySQL*" -ErrorAction SilentlyContinue) | Where-Object { $_.Name -match "MySQL[0-9]*" } | Select-Object -First 1

if (-not $mysqlService) {
    Print-Step "MySQL no esta instalado. Se instalara el asistente de MySQL..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        & winget install -e --id Oracle.MySQL --silent --accept-package-agreements --accept-source-agreements | Out-Host
    }
    $installer = @(
        "C:\Program Files (x86)\MySQL\MySQL Installer for Windows\MySQLInstaller.exe",
        "C:\Program Files\MySQL\MySQL Installer for Windows\MySQLInstaller.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $installer) {
        Write-Host "MySQL Installer no se instalo automaticamente." -ForegroundColor Red
        Write-Host "Descargalo de https://dev.mysql.com/downloads/installer/ e instala:" -ForegroundColor Red
        Write-Host "  MySQL Server 8.0 (con una contrasena para root que recuerdes)." -ForegroundColor Red
        Write-Host "Luego vuelve a ejecutar este instalador." -ForegroundColor Red
        Wait-Press "Presiona Enter para cerrar"
        exit 1
    }

    Write-Host "Se abrira el asistente de MySQL. Sigue estos pasos:" -ForegroundColor Cyan
    Write-Host "  1) Elige 'Developer Default' -> Next." -ForegroundColor Cyan
    Write-Host "  2) Pulsa 'Execute' para descargar e instalar MySQL Server." -ForegroundColor Cyan
    Write-Host "  3) Define una CONTRASENA para el usuario root y escribela en un papel." -ForegroundColor Cyan
    Write-Host "  4) Deja las demas opciones y pulsa Next, Execute y Finish." -ForegroundColor Cyan
    Write-Host "Este instalador espera aqui a que termines (hasta 10 minutos)..." -ForegroundColor Yellow
    Start-Process $installer

    $deadline = (Get-Date).AddMinutes(10)
    while ((Get-Date) -lt $deadline) {
        $svc = @(Get-Service -Name "MySQL*" -ErrorAction SilentlyContinue) | Where-Object { $_.Name -match "MySQL[0-9]*" } | Select-Object -First 1
        if ($svc) { $mysqlService = $svc; break }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 5
    }
    if (-not $mysqlService) {
        Write-Host ""
        Write-Host "No se detecto MySQL despues de la instalacion." -ForegroundColor Red
        Write-Host "Revisa MySQL Workbench y vuelve a ejecutar este instalador cuando este listo." -ForegroundColor Red
        Wait-Press "Presiona Enter para cerrar"
        exit 1
    }
}

if ($mysqlService.Status -ne "Running") {
    Start-Service $mysqlService.Name -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}
Print-Ok "MySQL: servicio $($mysqlService.Name) en ejecucion"

# Buscar el cliente mysql
$mysqlBin = $null
$cmdMysql = Get-Command mysql -ErrorAction SilentlyContinue
if ($cmdMysql) { $mysqlBin = $cmdMysql.Source }
if (-not $mysqlBin) {
    foreach ($d in @("C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe", "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe", "C:\Program Files\MySQL\MySQL Server 8.5\bin\mysql.exe")) {
        if (Test-Path $d) { $mysqlBin = $d; break }
    }
}
if (-not $mysqlBin) {
    Write-Host "No se encontro el cliente mysql. Instala 'MySQL Workbench' o agrega la carpeta bin de MySQL al PATH." -ForegroundColor Red
    Wait-Press "Presiona Enter para cerrar"
    exit 1
}
Print-Ok "Cliente mysql encontrado"

# ------------------------------------------------------------
# 3/8 - Conexion a la base de datos
# ------------------------------------------------------------
Print-Step "3/8 - Conexion a la base de datos"
$existingPass = ""
if (Test-Path "$projDir\.env") {
    $line = Get-Content "$projDir\.env" -ErrorAction SilentlyContinue | Where-Object { $_ -match "^DB_PASSWORD=" } | Select-Object -First 1
    if ($line) { $existingPass = $line.Substring($line.IndexOf("=") + 1) }
}

if ($existingPass -ne "") {
    $dbPass = Read-Host "Contrasena de root de MySQL (Enter para usar la existente)"
    if ($dbPass -eq "") { $dbPass = $existingPass }
} else {
    $dbPass = Read-Host "Contrasena de root de MySQL (dejala vacia si no tiene)"
}

$connOK = $false
for ($try = 1; $try -le 3 -and -not $connOK; $try++) {
    $env:MYSQL_PWD = $dbPass
    & $mysqlBin -u root -h 127.0.0.1 -e "SELECT 1" *> $null
    $connOK = ($LASTEXITCODE -eq 0)
    if (-not $connOK -and $try -lt 3) {
        $dbPass = Read-Host "No se pudo conectar. Vuelve a escribir la contrasena de root"
    }
}
if (-not $connOK) {
    Write-Host "No se pudo conectar a MySQL. Verifica el servicio y la contrasena." -ForegroundColor Red
    Wait-Press "Presiona Enter para cerrar"
    exit 1
}
Print-Ok "Conexion a MySQL correcta"

# ------------------------------------------------------------
# 4/8 - Crear la base de datos (e importar datos si vienen)
# ------------------------------------------------------------
Print-Step "4/8 - Creando la base de datos"
$env:MYSQL_PWD = $dbPass
& $mysqlBin -u root -h 127.0.0.1 -e "CREATE DATABASE IF NOT EXISTS sistema_inventario_huang CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
if ($LASTEXITCODE -ne 0) {
    Write-Host "No se pudo crear la base de datos." -ForegroundColor Red
    Wait-Press "Presiona Enter para cerrar"
    exit 1
}
Print-Ok "Base de datos 'sistema_inventario_huang' lista"

# Si viene el archivo datos_iniciales.sql, se importa (instalacion CON datos).
# Si no existe, se crea una base vacia (proyecto nuevo).
$datosIniciales = "$projDir\datos_iniciales.sql"
$importedData = $false
if (Test-Path $datosIniciales) {
    Print-Step "Importando datos desde datos_iniciales.sql (puede tardar)..."
    $env:MYSQL_PWD = $dbPass
    cmd /c "`"$mysqlBin`" -u root -h 127.0.0.1 --default-character-set=utf8mb4 sistema_inventario_huang < `"$datosIniciales`""
    if ($LASTEXITCODE -eq 0) {
        $importedData = $true
        Print-Ok "Datos importados correctamente (productos, clientes, ventas, usuarios...)"
    } else {
        Write-Host "Aviso: no se pudieron importar los datos. Se continuara con base vacia." -ForegroundColor Yellow
    }
} else {
    Print-Ok "No hay datos_iniciales.sql: se creara una base nueva vacia"
}

# ------------------------------------------------------------
# 5/8 - Entorno virtual y dependencias
# ------------------------------------------------------------
Print-Step "5/8 - Instalando dependencias (puede tardar unos minutos)"
if (-not (Test-Path "$projDir\venv\Scripts\python.exe")) {
    & $python -m venv "$projDir\venv"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudo crear el entorno virtual." -ForegroundColor Red
        Wait-Press "Presiona Enter para cerrar"
        exit 1
    }
}
& "$projDir\venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& "$projDir\venv\Scripts\pip.exe" install -r "$projDir\requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Reintentando sin PyMuPDF (opcional)..." -ForegroundColor Yellow
    $req = Get-Content "$projDir\requirements.txt" | Where-Object { $_ -notmatch "PyMuPDF" }
    [System.IO.File]::WriteAllText("$projDir\requirements_sin_pymupdf.txt", ($req -join "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
    & "$projDir\venv\Scripts\pip.exe" install -r "$projDir\requirements_sin_pymupdf.txt"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudieron instalar las dependencias." -ForegroundColor Red
        Wait-Press "Presiona Enter para cerrar"
        exit 1
    }
}
Print-Ok "Dependencias instaladas"

# ------------------------------------------------------------
# 6/8 - Configurar .env
# ------------------------------------------------------------
Print-Step "6/8 - Configurando archivo .env"
$secretChars = 48..57 + 65..90 + 97..122
$secretKey = -join ($secretChars | Get-Random -Count 48 | ForEach-Object { [char]$_ })

$tesseractCmd = ""
if (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe") { $tesseractCmd = "C:\Program Files\Tesseract-OCR\tesseract.exe" }
$mysqldumpPath = ""
foreach ($d in @("C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe", "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe", "C:\Program Files\MySQL\MySQL Server 8.5\bin\mysqldump.exe")) {
    if (Test-Path $d) { $mysqldumpPath = $d; break }
}

$envPath = "$projDir\.env"
if (Test-Path $envPath) {
    $content = Get-Content $envPath
    $content = $content | ForEach-Object {
        if ($_ -match "^DB_PASSWORD=") { "DB_PASSWORD=" + $dbPass }
        elseif ($_ -match "^DB_NAME=") { "DB_NAME=sistema_inventario_huang" }
        elseif ($_ -match "^PORT=") { "PORT=5010" }
        elseif ($_ -match "^SECRET_KEY=") { "SECRET_KEY=" + $secretKey }
        elseif ($_ -match "^TESSERACT_CMD=") { "TESSERACT_CMD=" + $tesseractCmd }
        elseif ($_ -match "^MYSQLDUMP_PATH=") { "MYSQLDUMP_PATH=" + $mysqldumpPath }
        else { $_ }
    }
} else {
    $content = @(
        "DB_HOST=127.0.0.1",
        "DB_PORT=3306",
        "DB_USER=root",
        "DB_PASSWORD=" + $dbPass,
        "DB_NAME=sistema_inventario_huang",
        "PORT=5010",
        "",
        "SECRET_KEY=" + $secretKey,
        "FLASK_ENV=development",
        "",
        "TESSERACT_CMD=" + $tesseractCmd,
        "",
        "SMTP_HOST=smtp.gmail.com",
        "SMTP_PORT=587",
        "SMTP_USER=",
        "SMTP_PASSWORD=",
        "ALERT_EMAIL_TO=",
        "",
        "MYSQLDUMP_PATH=" + $mysqldumpPath,
        "MAX_BACKUPS=30"
    )
}
[System.IO.File]::WriteAllText($envPath, ($content -join "`r`n") + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
Print-Ok ".env configurado"

# ------------------------------------------------------------
# 7/8 - Crear tablas y roles base (solo si la base esta vacia)
# ------------------------------------------------------------
if ($importedData) {
    Print-Step "7/8 - Datos ya importados"
    Print-Ok "La base ya trae tablas, roles, categorias y usuarios"
} else {
    Print-Step "7/8 - Creando tablas y datos base (roles y categorias)"
    & "$projDir\venv\Scripts\python.exe" "$projDir\init_db.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudieron crear las tablas. Revisa el .env (DB_USER/DB_PASSWORD)." -ForegroundColor Red
        Wait-Press "Presiona Enter para cerrar"
        exit 1
    }
    Print-Ok "Base de datos inicializada"
}

# ------------------------------------------------------------
# 8/8 - Usuario administrador (solo si la base es nueva)
# ------------------------------------------------------------
if ($importedData) {
    Print-Step "8/8 - Usuario administrador"
    Write-Host "  Se usan los usuarios que ya vienen en la base de datos importada." -ForegroundColor Cyan
    $username = "(usuarios existentes de la base importada)"
} else {
    Print-Step "8/8 - Usuario administrador"
    $username = Read-Host "Nombre de usuario del administrador (ej: admin)"
    $fullname = Read-Host "Nombre completo (ej: Ivan Teneta)"
    $pw1 = Read-Host "Contrasena" -AsSecureString
    $pw2 = Read-Host "Repite la contrasena" -AsSecureString
    $p1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw1))
    $p2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw2))
    if ($p1 -ne $p2 -or $p1 -eq "") {
        Write-Host "Las contrasenas no coinciden o estan vacias." -ForegroundColor Red
        Wait-Press "Presiona Enter para cerrar"
        exit 1
    }
    & "$projDir\venv\Scripts\python.exe" "$projDir\crear_admin.py" $username $fullname $p1 administrador
    Print-Ok "Usuario '$username' listo"
}

# ------------------------------------------------------------
# 8/8 - Accesos directos en el Escritorio
# ------------------------------------------------------------
Print-Step "8/8 - Accesos directos en el Escritorio"
$desktop = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell

$lnk1 = $ws.CreateShortcut("$desktop\Sistema de Facturacion Barbazul.lnk")
$lnk1.TargetPath = "$projDir\Iniciar_Sistema.vbs"
$lnk1.WorkingDirectory = $projDir
$lnk1.Save()

$lnk2 = $ws.CreateShortcut("$desktop\Detener Sistema Barbazul.lnk")
$lnk2.TargetPath = "$projDir\Detener_Sistema.vbs"
$lnk2.WorkingDirectory = $projDir
$lnk2.Save()
Print-Ok "Accesos directos creados"

# ------------------------------------------------------------
# OCR (opcional)
# ------------------------------------------------------------
if (-not (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe")) {
    $ocr = Read-Host "Instalar Tesseract OCR para leer facturas automaticamente? (s/N)"
    if ($ocr -match "^[sS]") {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) { & winget install -e --id UB-Mannheim.TesseractOCR --silent --accept-package-agreements --accept-source-agreements | Out-Host }
        else { Write-Host "Winget no disponible. El OCR se puede instalar luego." -ForegroundColor Yellow }
    }
}

# ------------------------------------------------------------
# Prueba final
# ------------------------------------------------------------
Print-Step "Verificando que el sistema arranque..."
Start-Process "$projDir\venv\Scripts\pythonw.exe" -ArgumentList "run_silencioso.py" -WorkingDirectory $projDir -WindowStyle Hidden
Start-Sleep -Seconds 8
try {
    $resp = Invoke-WebRequest "http://127.0.0.1:5010" -UseBasicParsing -TimeoutSec 8
    Print-Ok "El sistema responde correctamente (HTTP $($resp.StatusCode))"
} catch {
    Write-Host "Aviso: el sistema no respondio en la prueba. Revisa el archivo server.log." -ForegroundColor Red
}
@(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue) | Where-Object { $_.CommandLine -like "*$projDir*" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
$env:MYSQL_PWD = ""

Print-Banner "Instalacion completada!"
Write-Host "  Para ABRIR el sistema: doble clic en el icono"
Write-Host "      'Sistema de Facturacion Barbazul' del Escritorio."
Write-Host "  Para DETENERLO: doble clic en 'Detener Sistema Barbazul'."
Write-Host ""
Write-Host "  Usuario: $username"
Write-Host ""
Wait-Press "Presiona Enter para cerrar"
