Option Explicit

Dim fso, WshShell, projDir, pythonw, cmd, i, up

Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

projDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Localiza el pythonw.exe a usar (prioridad: venv del proyecto, luego Python instalado).
Function FindPythonw()
  Dim paths, p, shell
  Set shell = CreateObject("WScript.Shell")

  ' 1) Entorno virtual del proyecto
  If fso.FileExists(projDir & "\venv\Scripts\pythonw.exe") Then
    FindPythonw = projDir & "\venv\Scripts\pythonw.exe"
    Exit Function
  End If

  ' 2) Ruta registrada de Python en el registro (HKLM y HKCU)
  On Error Resume Next
  p = shell.RegRead("HKLM\SOFTWARE\Python\PythonCore\3.12\InstallPath\")
  If Err.Number = 0 And p <> "" And fso.FileExists(p & "pythonw.exe") Then
    FindPythonw = p & "pythonw.exe"
    Err.Clear
    Exit Function
  End If
  Err.Clear
  p = shell.RegRead("HKCU\SOFTWARE\Python\PythonCore\3.12\InstallPath\")
  If Err.Number = 0 And p <> "" And fso.FileExists(p & "pythonw.exe") Then
    FindPythonw = p & "pythonw.exe"
    Err.Clear
    Exit Function
  End If
  Err.Clear
  On Error GoTo 0

  ' 3) Ubicaciones comunes de instalacion
  paths = Array( _
    "C:\Users\leo-p\AppData\Local\Programs\Python\Python312\pythonw.exe", _
    "C:\Python312\pythonw.exe", _
    "C:\Program Files\Python312\pythonw.exe", _
    "C:\Python311\pythonw.exe", _
    "C:\Program Files\Python311\pythonw.exe")

  For Each p In paths
    If fso.FileExists(p) Then
      FindPythonw = p
      Exit Function
    End If
  Next

  ' 4) Ultimo recurso: que Windows lo busque en el PATH
  FindPythonw = "pythonw.exe"
End Function

pythonw = FindPythonw()

' Comprueba si el servidor responde. Usa WinHttp con tiempo limite para
' NO quedarse colgado (el XMLHTTP normal puede tardar por el proxy de Windows).
Function ServerUp()
  Dim h, errNum, st
  On Error Resume Next
  Set h = Nothing
  Set h = CreateObject("WinHttp.WinHttpRequest.5.1")
  If Err.Number <> 0 Then
    Err.Clear
    Set h = CreateObject("WinHttp.WinHttpRequest")
  End If
  On Error GoTo 0
  If h Is Nothing Then
    ServerUp = False
    Exit Function
  End If

  On Error Resume Next
  h.SetTimeouts 1000, 1000, 1000, 2500
  h.Open "GET", "http://127.0.0.1:5010/", False
  h.Send
  errNum = Err.Number
  Err.Clear
  ServerUp = False
  If errNum = 0 Then
    st = h.Status
    If Err.Number = 0 And st = 200 Then
      ServerUp = True
    End If
  End If
  Set h = Nothing
  Err.Clear
  On Error GoTo 0
End Function

up = ServerUp()

If Not up Then
  cmd = "cmd /c cd /d """ & projDir & """ && """ & pythonw & """ run_silencioso.py > server.log 2>&1"
  WshShell.Run cmd, 0, False
  For i = 1 To 120
    WScript.Sleep 500
    up = ServerUp()
    If up Then Exit For
  Next
End If

WshShell.Run "http://127.0.0.1:5010", 1, False

If Not up Then
  MsgBox "El sistema no respondio al abrirse." & vbCrLf & vbCrLf & _
         "Revisa que MySQL este corriendo (Servicios -> MySQL80 -> Iniciar)." & vbCrLf & _
         "Detalles en el archivo server.log de la carpeta del proyecto.", _
         48, "Sistema de Facturacion Barbazul"
End If
