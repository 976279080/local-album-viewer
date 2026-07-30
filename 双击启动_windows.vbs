' Local Album Viewer - Windows Launcher
' Auto-restart service, then open browser (fast path: no update check)

Dim objShell, objFSO, objWMI, strBasePath, strPythonPath, strMainPath
Dim strCmd, intReturn, i, bReady

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get script directory
strBasePath = objFSO.GetParentFolderName(WScript.ScriptFullName)

' main.py path
strMainPath = strBasePath & "\.bin\src\main.py"

' Check if main.py exists
If Not objFSO.FileExists(strMainPath) Then
    MsgBox "Cannot find main.py!" & vbCrLf & _
           "Please ensure .bin\src\main.py exists", vbCritical, "Error"
    WScript.Quit 1
End If

' Prefer pythonw.exe (no console window), fallback to python.exe
strPythonPath = strBasePath & "\.bin\python\pythonw.exe"
If Not objFSO.FileExists(strPythonPath) Then
    strPythonPath = strBasePath & "\.bin\python\python.exe"
    If Not objFSO.FileExists(strPythonPath) Then
        MsgBox "Cannot find embedded Python!" & vbCrLf & _
               "Please put Python into .bin\python\ directory", vbCritical, "Error"
        WScript.Quit 1
    End If
End If

' ============================================================
' Hide files that users don't need to see
' ============================================================
On Error Resume Next
objShell.Run "cmd /c attrib +h """ & strBasePath & "\README.md""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\version.json""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.bin""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.user_data""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.trae""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.tests""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.pending_update""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.bin_update""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.bin_backup""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.gitignore""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.release""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\generate_license.html""", 0, True
On Error GoTo 0

' Kill old process on port 8089
On Error Resume Next
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")
Dim colProcesses, objProcess
Set colProcesses = objWMI.ExecQuery _
    ("SELECT * FROM Win32_Process WHERE CommandLine LIKE '%main.py%'")
For Each objProcess In colProcesses
    objProcess.Terminate
Next
WScript.Sleep 300
On Error GoTo 0

' Build command line
strCmd = """" & strPythonPath & """ """ & strMainPath & """"

' Start silently (window mode = 0 hidden, wait = False)
intReturn = objShell.Run(strCmd, 0, False)

' Poll port (check every 200ms, max 10 seconds)
bReady = False
For i = 1 To 50
    WScript.Sleep 200
    Dim http
    On Error Resume Next
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.SetTimeouts 500, 500, 500, 500
    http.Open "GET", "http://localhost:8089/api/summary", False
    http.Send
    If Err.Number = 0 And http.Status = 200 Then
        bReady = True
        Exit For
    End If
    On Error GoTo 0
Next

' Open browser
If bReady Then
    objShell.Run "http://localhost:8089", 1, False
Else
    MsgBox "Service startup timeout, please check the log", vbExclamation, "Warning"
End If

Set objFSO = Nothing
Set objShell = Nothing
