#Requires -Version 5.1
<#
.SYNOPSIS
    Diagnóstico de solo lectura para localizar la base de datos de un sistema legado.

.DESCRIPTION
    Este script NO modifica, borra ni detiene nada. Solo recopila información del equipo:
      - Servicios de bases de datos y rutas de instalación.
      - Puertos de base de datos escuchando y proceso que los usa.
      - Programas instalados, tareas programadas y programas de inicio.
      - ODBC, instancias de SQL Server y configuraciones (my.ini, pg_hba.conf, etc.).
      - Archivos de datos y respaldos (*.mdb, *.accdb, *.db, *.sqlite, *.fdb, *.dbf,
        *.mdf, *.ldf, *.ibd, *.sql, *.bak, etc.).
      - Posibles cadenas de conexión, con las contraseñas enmascaradas.

    Genera una carpeta y un ZIP en el Escritorio con el reporte y los CSV.

.PARAMETER MinutosEscaneo
    Tiempo máximo de búsqueda de archivos. Por defecto 6 minutos.

.PARAMETER Salida
    Carpeta de salida. Por defecto: Escritorio\Diagnostico_Legacy_<fecha>.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\diagnostico_sistema_legacy.ps1

.NOTES
    Recomendado ejecutarlo como Administrador para leer toda la información.
    No requiere credenciales de la base de datos.
#>

param(
    [int]$MinutosEscaneo = 6,
    [string]$Salida = ""
)

$ErrorActionPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
if ([string]::IsNullOrWhiteSpace($Salida)) {
    $escritorio = [Environment]::GetFolderPath("Desktop")
    if ([string]::IsNullOrWhiteSpace($escritorio) -or -not (Test-Path -LiteralPath $escritorio)) {
        $escritorio = $PSScriptRoot
    }
    $Salida = Join-Path $escritorio ("Diagnostico_Legacy_" + $timestamp)
}
New-Item -ItemType Directory -Path $Salida -Force | Out-Null

$reportPath = Join-Path $Salida "reporte.txt"
$lineasReporte = New-Object System.Collections.Generic.List[string]
$fechaLimite = (Get-Date).AddMinutes($MinutosEscaneo)
$script:fechaLimiteFase = $null
$script:truncado = $false
$script:configEncontradas = New-Object System.Collections.Generic.List[object]
$script:archivosDatos = New-Object System.Collections.Generic.List[object]

function Enmascarar-Secreto {
    param([string]$Texto)
    if ($null -eq $Texto) { return "" }
    $t = [regex]::Replace($Texto, '(?i)\b(password|passwd|pwd|clave|contrase(?:n|ñ)a|secret|token)\b(\s*[:=]\s*)([^;,"'']+)', '$1$2***')
    $t = [regex]::Replace($t, '(?i)(\w+://[^:\s/]+:)([^@\s/]+)(@)', '$1***$3')
    return $t
}

function Escribir {
    param([string]$Texto = "")
    $limpio = Enmascarar-Secreto $Texto
    $lineasReporte.Add($limpio)
    Write-Host $limpio
}

function Seccion {
    param([string]$Titulo)
    Escribir ""
    Escribir ("=" * 72)
    Escribir ("  " + $Titulo)
    Escribir ("=" * 72)
}

function TiempoAgotado {
    $limite = $fechaLimite
    if ($null -ne $script:fechaLimiteFase) { $limite = $script:fechaLimiteFase }
    return ((Get-Date) -gt $limite)
}

function Ruta-Excluida {
    param([string]$Ruta)
    if ([string]::IsNullOrWhiteSpace($Ruta)) { return $true }
    $r = $Ruta.ToLowerInvariant()
    $excluir = @(
        '\windows\winsxs', '\windows\servicing', '\windows\assembly', '\windows\microsoft.net',
        '\$recycle.bin', '\system volume information', '\node_modules', '\.git\',
        '\appdata\local\microsoft\edge', '\appdata\local\google\chrome',
        '\appdata\local\packages', '\appdata\local\temp', '\windows\temp'
    )
    foreach ($e in $excluir) {
        if ($r.Contains($e)) { return $true }
    }
    return $false
}

$extensionesDatos = @(
    ".mdb", ".accdb", ".db", ".sqlite", ".sqlite3", ".fdb", ".gdb", ".dbf",
    ".mdf", ".ldf", ".ndf", ".ib", ".ibd", ".frm", ".myi", ".myd", ".ibdata1",
    ".sql", ".bak", ".dump", ".backup"
)
$extensionesConfig = @(
    ".ini", ".cnf", ".conf", ".config", ".xml", ".json", ".env", ".properties",
    ".yaml", ".yml", ".udl", ".dsn", ".bat", ".cmd", ".vbs", ".ps1"
)

# ============================================================
# 1. DATOS DEL EQUIPO
# ============================================================
$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem

Escribir "DIAGNOSTICO DE SISTEMA LEGADO - SOLO LECTURA"
Escribir "Generado: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')"
Escribir "Equipo: $($env:COMPUTERNAME)"
Escribir "Usuario: $($env:USERDOMAIN)\$($env:USERNAME)"
Escribir "Ejecutado como administrador: $(if ($esAdmin) { 'SI' } else { 'NO (algunas secciones pueden estar incompletas)' })"
Escribir "Windows: $($os.Caption) $($os.Version) $($os.OSArchitecture)"
Escribir "Fabricante/Modelo: $($cs.Manufacturer) / $($cs.Model)"
Escribir "Dominio/Grupo: $($cs.Domain)"
Escribir "Tiempo maximo de busqueda de archivos: $MinutosEscaneo minuto(s)"

# ============================================================
# 2. SERVICIOS RELACIONADOS CON BASES DE DATOS
# ============================================================
Seccion "SERVICIOS DE BASES DE DATOS Y APLICACIONES"
$patronDB = '(?i)mysql|maria|postgres|sql server|mssql|firebird|interbase|oracle|mongo|sybase|informix|db2'
$servicios = Get-CimInstance Win32_Service | Where-Object {
    $_.Name -match $patronDB -or $_.DisplayName -match $patronDB -or $_.PathName -match $patronDB
} | Sort-Object DisplayName

if ($servicios) {
    foreach ($s in $servicios) {
        Escribir "Servicio: $($s.Name) | $($s.DisplayName)"
        Escribir "  Estado: $($s.State) | Inicio: $($s.StartMode)"
        Escribir "  Ejecutable: $($s.PathName)"
        Escribir "  Cuenta: $($s.StartName)"
    }
} else {
    Escribir "No se encontraron servicios de bases de datos por nombre."
}

# Exportar todos los servicios (util para revisar aplicaciones legacy)
$todosServicios = Get-CimInstance Win32_Service | Select-Object Name, DisplayName, State, StartMode, StartName, PathName
$todosServicios | Export-Csv -Path (Join-Path $Salida "servicios.csv") -NoTypeInformation -Encoding UTF8

# ============================================================
# 3. PUERTOS DE BASE DE DATOS Y PROCESOS
# ============================================================
Seccion "PUERTOS DE BASE DE DATOS ESCUCHANDO"
$puertosDB = @(1433, 3306, 3307, 5432, 5433, 3050, 3051, 1521, 5000, 2638, 27017, 6379)
$conexiones = Get-NetTCPConnection -State Listen | Where-Object { $puertosDB -contains $_.LocalPort } | Sort-Object LocalPort
$filasPuertos = New-Object System.Collections.Generic.List[object]
if ($conexiones) {
    foreach ($c in $conexiones) {
        $proc = Get-Process -Id $c.OwningProcess
        $cmd = Get-CimInstance Win32_Process -Filter "ProcessId = $($c.OwningProcess)"
        $fila = [pscustomobject]@{
            Puerto       = $c.LocalPort
            Direccion    = $c.LocalAddress
            PID          = $c.OwningProcess
            Proceso      = if ($proc) { $proc.ProcessName } else { "" }
            RutaProceso  = if ($cmd) { $cmd.ExecutablePath } else { "" }
        }
        $filasPuertos.Add($fila)
        Escribir "Puerto $($fila.Puerto) | $($fila.Direccion) | PID $($fila.PID) | $($fila.Proceso)"
        if ($fila.RutaProceso) { Escribir "  Ruta: $($fila.RutaProceso)" }
    }
} else {
    Escribir "No se detectaron puertos de base de datos escuchando."
}
$filasPuertos | Export-Csv -Path (Join-Path $Salida "puertos.csv") -NoTypeInformation -Encoding UTF8

# ============================================================
# 4. INSTANCIAS DE SQL SERVER
# ============================================================
Seccion "INSTANCIAS DE SQL SERVER"
$instanciasSQL = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL'
if ($instanciasSQL) {
    $propiedades = $instanciasSQL.PSObject.Properties | Where-Object { $_.Name -notmatch '^(PS|Cim|__)' }
    if ($propiedades) {
        foreach ($p in $propiedades) {
            $instancia = $p.Value
            $setup = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\$instancia\Setup"
            Escribir "Instancia: $($p.Name) -> $instancia"
            if ($setup) {
                Escribir "  Version: $($setup.Version) | Edicion: $($setup.Edition)"
                Escribir "  DataRoot: $($setup.SQLDataRoot)"
                Escribir "  BinRoot: $($setup.SQLBinRoot)"
            }
        }
    } else {
        Escribir "No se encontraron instancias registradas."
    }
} else {
    Escribir "No se detectó SQL Server por registro."
}

# ============================================================
# 5. PROGRAMAS INSTALADOS
# ============================================================
Seccion "PROGRAMAS INSTALADOS RELACIONADOS"
$rutasUninstall = @(
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$programas = @()
foreach ($ruta in $rutasUninstall) {
    $programas += (Get-ItemProperty -Path $ruta | Where-Object { $_.DisplayName } | Select-Object DisplayName, DisplayVersion, Publisher, InstallLocation)
}
$programas = $programas | Sort-Object DisplayName -Unique
$programas | Export-Csv -Path (Join-Path $Salida "programas.csv") -NoTypeInformation -Encoding UTF8

$patronProgramas = '(?i)mysql|maria|postgres|sql server|firebird|interbase|access|office|sistema|factur|inventar|contab|pos|punto de venta|fox|clipper|delphi|visual basic|vb6|\.net|sage|contifico|microsip|aspel|sap|odoo'
$programasClave = $programas | Where-Object {
    "$($_.DisplayName) $($_.Publisher)" -match $patronProgramas
}
if ($programasClave) {
    foreach ($p in $programasClave) {
        Escribir "Programa: $($p.DisplayName) | Version: $($p.DisplayVersion) | Editor: $($p.Publisher)"
        if ($p.InstallLocation) { Escribir "  Carpeta: $($p.InstallLocation)" }
    }
} else {
    Escribir "No se encontraron programas con nombres relacionados. Revisa programas.csv completo."
}

# ============================================================
# 6. ODBC (DSN)
# ============================================================
Seccion "ORIGENES DE DATOS ODBC"
if (Get-Command Get-OdbcDsn -ErrorAction SilentlyContinue) {
    $dsns = Get-OdbcDsn
    if ($dsns) {
        foreach ($d in $dsns) {
            $attrs = @()
            if ($d.Attribute -is [System.Collections.IDictionary]) {
                foreach ($clave in $d.Attribute.Keys) {
                    $attrs += "$clave=$($d.Attribute[$clave])"
                }
            } elseif ($d.Attribute) {
                foreach ($prop in $d.Attribute.PSObject.Properties) {
                    if ($prop.Name -notmatch '^(PS|Cim|__)') {
                        $attrs += "$($prop.Name)=$($prop.Value)"
                    }
                }
            }
            Escribir "DSN: $($d.Name) | Tipo: $($d.DsnType) | Driver: $($d.DriverName)"
            if ($attrs.Count -gt 0) { Escribir ("  " + (Enmascarar-Secreto ($attrs -join '; '))) }
        }
    } else {
        Escribir "No hay DSN ODBC configurados."
    }
} else {
    Escribir "El comando Get-OdbcDsn no esta disponible en este equipo."
}

# ============================================================
# 7. PROGRAMAS DE INICIO Y TAREAS PROGRAMADAS
# ============================================================
Seccion "PROGRAMAS DE INICIO"
$inicio = Get-CimInstance Win32_StartupCommand
if ($inicio) {
    foreach ($i in $inicio) {
        Escribir "Inicio: $($i.Name) | $($i.Location) | Usuario: $($i.User)"
        Escribir "  Comando: $($i.Command)"
    }
} else {
    Escribir "No se encontraron programas de inicio."
}

Seccion "TAREAS PROGRAMADAS RELACIONADAS"
if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
    $tareas = Get-ScheduledTask | Where-Object {
        $_.TaskName -match '(?i)backup|respaldo|mysql|sql|factur|sistema|invent|pos|contab'
    }
    if ($tareas) {
        foreach ($t in $tareas) {
            $acciones = @()
            foreach ($a in $t.Actions) {
                $acciones += ("$($a.Execute) $($a.Arguments)").Trim()
            }
            Escribir "Tarea: $($t.TaskName) | Ruta: $($t.TaskPath) | Estado: $($t.State)"
            if ($acciones.Count -gt 0) { Escribir ("  Accion: " + ($acciones -join ' | ')) }
        }
    } else {
        Escribir "No se encontraron tareas relacionadas."
    }
} else {
    Escribir "El comando Get-ScheduledTask no esta disponible."
}

# ============================================================
# 8. UNIDADES Y ESPACIO EN DISCO
# ============================================================
Seccion "ESPACIO EN DISCO"
Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Root -match '^[A-Za-z]:' } | ForEach-Object {
    $total = $_.Used + $_.Free
    if ($total -gt 0) {
        Escribir ("Unidad {0} | Total: {1:N1} GB | Libre: {2:N1} GB | Usado: {3:N1} GB" -f $_.Root, ($total/1GB), ($_.Free/1GB), ($_.Used/1GB))
    }
}

# ============================================================
# 9. RUTAS A ESCANEAR
# ============================================================
$rutas = New-Object System.Collections.Generic.List[object]
$rutasVistas = @{}

function Agregar-Ruta {
    param([string]$Ruta, [int]$Profundidad, [string]$Etiqueta)
    if ([string]::IsNullOrWhiteSpace($Ruta)) { return }
    if (-not (Test-Path -LiteralPath $Ruta)) { return }
    if (Ruta-Excluida $Ruta) { return }
    $clave = $Ruta.TrimEnd('\').ToLowerInvariant()
    if ($rutasVistas.ContainsKey($clave)) { return }
    $rutasVistas[$clave] = $true
    $rutas.Add([pscustomobject]@{ Ruta = $Ruta; Profundidad = $Profundidad; Etiqueta = $Etiqueta })
}

Agregar-Ruta $env:ProgramData 6 "ProgramData"
Agregar-Ruta (Join-Path $env:USERPROFILE "Documents") 6 "Documentos"
Agregar-Ruta (Join-Path $env:USERPROFILE "Desktop") 6 "Escritorio"
Agregar-Ruta (Join-Path $env:USERPROFILE "Downloads") 6 "Descargas"
Agregar-Ruta (Join-Path $env:PUBLIC "Documents") 6 "Documentos publicos"
Agregar-Ruta $env:APPDATA 5 "AppData Roaming"
Agregar-Ruta $env:LOCALAPPDATA 4 "AppData Local"

foreach ($carpeta in @("C:\xampp", "C:\wamp", "C:\wamp64", "C:\laragon", "C:\AppServ", "C:\EasyPHP", "C:\UniformServer", "C:\Bitnami")) {
    Agregar-Ruta $carpeta 8 "Servidor local"
}

# Carpetas personalizadas en la raiz del disco del sistema
$excluirRaiz = @('windows','program files','program files (x86)','programdata','users','$recycle.bin','system volume information','recovery','perflogs','boot','efi','intel','amd','nvidia','temp','$winreagent','msocache','config.msi','onedrivetemp')
Get-ChildItem -LiteralPath "$env:SystemDrive\" -Directory -Force | Where-Object { $excluirRaiz -notcontains $_.Name.ToLowerInvariant() } | ForEach-Object {
    Agregar-Ruta $_.FullName 6 "Carpeta personalizada"
}

# Otras unidades fijas
Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Root -match '^[A-Za-z]:\\?$' -and $_.Root -notmatch "^$([regex]::Escape($env:SystemDrive))" } | ForEach-Object {
    Agregar-Ruta $_.Root 4 "Otra unidad"
}

# Program Files al final: suele ser la carpeta mas grande y con menos configuraciones utiles
Agregar-Ruta $env:ProgramFiles 6 "Program Files"
Agregar-Ruta ${env:ProgramFiles(x86)} 6 "Program Files (x86)"

Escribir ""
Escribir "Rutas que se van a revisar: $($rutas.Count)"

# ============================================================
# 10. BUSCAR CONFIGURACIONES Y POSIBLES CREDENCIALES
# ============================================================
Seccion "CONFIGURACIONES Y POSIBLES CADENAS DE CONEXION"
$script:fechaLimiteFase = (Get-Date).AddMinutes([Math]::Max(0.5, $MinutosEscaneo * 0.6))
if ($script:fechaLimiteFase -gt $fechaLimite) { $script:fechaLimiteFase = $fechaLimite }
foreach ($r in $rutas) {
    if (TiempoAgotado) { $script:truncado = $true; break }
    $archivos = Get-ChildItem -LiteralPath $r.Ruta -Recurse -Depth ([Math]::Min($r.Profundidad, 5)) -File -Force -ErrorAction SilentlyContinue
    foreach ($a in $archivos) {
        if (TiempoAgotado) { $script:truncado = $true; break }
        if (Ruta-Excluida $a.FullName) { continue }
        if ($a.Name -ieq "diagnostico_sistema_legacy.ps1") { continue }
        if ($a.FullName.StartsWith($Salida, [System.StringComparison]::OrdinalIgnoreCase)) { continue }
        $ext = $a.Extension.ToLowerInvariant()
        if ($extensionesConfig -notcontains $ext) { continue }
        if ($a.Length -gt 512KB) { continue }
        $contenido = Get-Content -LiteralPath $a.FullName -TotalCount 400 -ErrorAction SilentlyContinue
        if (-not $contenido) { continue }
        $nombreClave = $a.Name -match '(?i)^(my\.ini|my\.cnf|pg_hba\.conf|pg_service\.conf|web\.config|app\.config|appsettings.*\.json|connectionstrings.*|\.env.*|.*\.dsn|.*\.udl)$'
        $numero = 0
        foreach ($linea in $contenido) {
            $numero++
            $limpia = $linea.Trim()
            if ($limpia -match '^(#|//|REM\b|::)') { continue }
            $coinc = [regex]::Matches($linea, '(?i)\b(server|data source|datasource|database|initial catalog|uid|user id|username|password|passwd|pwd|provider|dsn|datadir|dbname|driver)\b\s*=')
            $tipos = @($coinc | ForEach-Object { $_.Groups[1].Value.ToLowerInvariant() } | Select-Object -Unique)
            if (($tipos.Count -ge 2) -or ($nombreClave -and $tipos.Count -ge 1)) {
                $texto = $limpia
                if ($texto.Length -gt 300) { $texto = $texto.Substring(0, 300) + "..." }
                $script:configEncontradas.Add([pscustomobject]@{
                    Archivo   = $a.FullName
                    Linea     = $numero
                    Contenido = (Enmascarar-Secreto $texto)
                })
            }
        }
    }
    if ($script:truncado) { break }
}

if ($script:configEncontradas.Count -gt 0) {
    $script:configEncontradas | Export-Csv -Path (Join-Path $Salida "configuraciones.csv") -NoTypeInformation -Encoding UTF8
    Escribir "Total de lineas candidatas: $($script:configEncontradas.Count)"
    Escribir "Se muestran las primeras 150. El resto esta en configuraciones.csv."
    $script:configEncontradas | Select-Object -First 150 | ForEach-Object {
        Escribir "  $($_.Archivo) : linea $($_.Linea)"
        Escribir "    $($_.Contenido)"
    }
} else {
    Escribir "No se encontraron lineas de conexion en configuraciones."
    "Archivo,Linea,Contenido" | Set-Content -LiteralPath (Join-Path $Salida "configuraciones.csv") -Encoding UTF8
}

# ============================================================
# 11. BUSCAR ARCHIVOS DE DATOS
# ============================================================
Seccion "ARCHIVOS DE DATOS Y RESPALDOS ENCONTRADOS"
$script:fechaLimiteFase = $fechaLimite
foreach ($r in $rutas) {
    if (TiempoAgotado) { $script:truncado = $true; break }
    Escribir "Revisando: $($r.Ruta) ..."
    $archivos = Get-ChildItem -LiteralPath $r.Ruta -Recurse -Depth $r.Profundidad -File -Force -ErrorAction SilentlyContinue
    foreach ($a in $archivos) {
        if (TiempoAgotado) { $script:truncado = $true; break }
        if (Ruta-Excluida $a.FullName) { continue }
        $ext = $a.Extension.ToLowerInvariant()
        $nombre = $a.Name.ToLowerInvariant()
        if ($extensionesDatos -contains $ext -or $nombre -eq "ibdata1") {
            $script:archivosDatos.Add([pscustomobject]@{
                Origen      = $r.Etiqueta
                Archivo     = $a.FullName
                Extension   = $ext
                TamanoMB    = [math]::Round($a.Length / 1MB, 2)
                Modificado  = $a.LastWriteTime.ToString("yyyy-MM-dd HH:mm")
            })
        }
    }
    if ($script:truncado) { break }
}

if ($script:archivosDatos.Count -gt 0) {
    $script:archivosDatos | Sort-Object TamanoMB -Descending | Export-Csv -Path (Join-Path $Salida "archivos_datos.csv") -NoTypeInformation -Encoding UTF8
    Escribir "Total de archivos encontrados: $($script:archivosDatos.Count)"
    Escribir "Los 60 mas grandes:"
    $script:archivosDatos | Sort-Object TamanoMB -Descending | Select-Object -First 60 | ForEach-Object {
        Escribir ("  [{0,8:N2} MB] {1}  ({2})" -f $_.TamanoMB, $_.Archivo, $_.Modificado)
    }
} else {
    Escribir "No se encontraron archivos con extensiones de base de datos."
    "Origen,Archivo,Extension,TamanoMB,Modificado" | Set-Content -LiteralPath (Join-Path $Salida "archivos_datos.csv") -Encoding UTF8
}

# ============================================================
# 12. ARCHIVOS my.ini / pg_hba.conf ESPECIFICOS
# ============================================================
Seccion "CONFIGURACIONES ESPECIFICAS DE BASE DE DATOS"
$configsConocidas = @()
foreach ($s in $servicios) {
    if ($s.PathName -match '(?i)--defaults-file\s*=\s*"?([^"\s]+)') {
        $configsConocidas += $matches[1]
    }
}
$configsConocidas += @(
    "C:\ProgramData\MySQL\MySQL Server 8.0\my.ini",
    "C:\ProgramData\MySQL\MySQL Server 5.7\my.ini",
    "C:\xampp\mysql\bin\my.ini",
    "C:\wamp64\bin\mysql\mysql8.0.31\my.ini"
)
$configsConocidas = $configsConocidas | Select-Object -Unique
foreach ($cfg in $configsConocidas) {
    if (Test-Path -LiteralPath $cfg) {
        Escribir "Configuracion: $cfg"
        Get-Content -LiteralPath $cfg -TotalCount 250 | Where-Object {
            $_ -match '(?i)datadir|port|bind-address|socket|basedir|server-id'
        } | ForEach-Object { Escribir ("  " + $_.Trim()) }
    }
}

# ============================================================
# 13. CIERRE
# ============================================================
Seccion "FIN DEL DIAGNOSTICO"
if ($script:truncado) {
    Escribir "AVISO: la busqueda de archivos alcano el tiempo maximo ($MinutosEscaneo min)."
    Escribir "Si no aparecen los datos, ejecuta de nuevo con mas tiempo, por ejemplo:"
    Escribir "  .\diagnostico_sistema_legacy.ps1 -MinutosEscaneo 20"
} else {
    Escribir "Busqueda completada sin alcanzar el tiempo maximo."
}
Escribir ""
Escribir "Este reporte enmascara contrasenas, pero puede contener nombres de servidores,"
Escribir "rutas y nombres de bases de datos. Compartelo solo con personas autorizadas."
Escribir ""
Escribir "Archivos generados:"
foreach ($nombre in @("reporte.txt", "servicios.csv", "puertos.csv", "programas.csv", "archivos_datos.csv", "configuraciones.csv")) {
    if ($nombre -eq "reporte.txt" -or (Test-Path -LiteralPath (Join-Path $Salida $nombre))) {
        Escribir "  $nombre"
    }
}

$lineasReporte | Set-Content -LiteralPath $reportPath -Encoding UTF8

# Crear ZIP para enviar
$zipPath = $Salida.TrimEnd('\') + ".zip"
try {
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $Salida "*") -DestinationPath $zipPath -CompressionLevel Optimal -Force
    $zipMensaje = "ZIP generado: $zipPath"
} catch {
    $zipMensaje = "No se pudo crear el ZIP: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " DIAGNOSTICO TERMINADO" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Carpeta: $Salida" -ForegroundColor Cyan
Write-Host $zipMensaje -ForegroundColor Cyan
Write-Host ""
Write-Host "Envia el ZIP al desarrollador para analizarlo." -ForegroundColor Yellow
Write-Host "El script no modifico nada del sistema." -ForegroundColor Yellow
