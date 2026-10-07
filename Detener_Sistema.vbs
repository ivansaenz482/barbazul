Option Explicit

Dim fso, WshShell, projDir, psFile, fout
Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

projDir = fso.GetParentFolderName(WScript.ScriptFullName)
psFile = projDir & "\detener.ps1"

Set fout = fso.CreateTextFile(psFile, True)
fout.WriteLine "$c = Get-NetTCPConnection -LocalPort 5010 -State Listen -ErrorAction SilentlyContinue"
fout.WriteLine "if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }"
fout.WriteLine "$proj = '" & projDir & "'"
fout.WriteLine "Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($proj) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
fout.WriteLine "Get-CimInstance Win32_Process -Filter 'Name=''pythonw.exe''' | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($proj) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
fout.Close()

WshShell.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & psFile & """", 0, True

WshShell.Popup "El Sistema de Facturación Barbazul se ha detenido.", 2, "Barbazul", 64
