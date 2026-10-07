$c = Get-NetTCPConnection -LocalPort 5010 -State Listen -ErrorAction SilentlyContinue
if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }
$proj = 'C:\Users\leo-p\Downloads\proyecto_inventario_COPIA'
Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($proj) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -Filter 'Name=''pythonw.exe''' | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($proj) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
