' Local Album Viewer - Windows Launcher
' Auto-restart service, then open browser (fast path: no update check)

Dim objShell, objFSO, objWMI, strBasePath, strPythonPath, strMainPath
Dim strCmd, intReturn, i, bReady

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get script directory
strBasePath = objFSO.GetParentFolderName(WScript.ScriptFullName)

' ============================================================
' 一、清理无用文件：只删 .release\.bin.zip（下载解压完就无用了）
' ============================================================
On Error Resume Next
If objFSO.FileExists(strBasePath & "\.release\.bin.zip") Then
    objFSO.DeleteFile strBasePath & "\.release\.bin.zip", True
End If
On Error GoTo 0

' ============================================================
' 二、白名单隐藏：根目录只保留
'   ✅ 首次单击启动_mac.command / 双击启动_windows.vbs / data
'   其他所有文件/文件夹一律隐藏（包括 .user_data / .bin / .release / version.json / README.md / .git 等）
' ============================================================
Dim MAC_LAUNCHER, WIN_LAUNCHER, DATA_DIR_NAME, HIDDEN_ATTR, STR_COMP_IGNORE_CASE
MAC_LAUNCHER = "首次单击启动_mac.command"
WIN_LAUNCHER = "双击启动_windows.vbs"
DATA_DIR_NAME = "data"
HIDDEN_ATTR = 2  ' Windows FileAttribute：Hidden = 2
STR_COMP_IGNORE_CASE = 1  ' 等价于 vbTextCompare，数字字面量避免编码解析问题

On Error Resume Next
If objFSO.FileExists(strBasePath & "\.release\.bin.zip") Then
    objFSO.DeleteFile strBasePath & "\.release\.bin.zip", True
End If
On Error GoTo 0

Dim objFolder, colItems, objItem, strName, bKeep
Set objFolder = objFSO.GetFolder(strBasePath)

' 先处理所有文件
Set colItems = objFolder.Files
For Each objItem In colItems
    strName = objItem.Name
    bKeep = False
    If StrComp(strName, MAC_LAUNCHER, STR_COMP_IGNORE_CASE) = 0 Then bKeep = True
    If StrComp(strName, WIN_LAUNCHER, STR_COMP_IGNORE_CASE) = 0 Then bKeep = True
    If bKeep Then
        objItem.Attributes = objItem.Attributes And Not HIDDEN_ATTR
    Else
        objItem.Attributes = objItem.Attributes Or HIDDEN_ATTR
    End If
Next

' 再处理所有子文件夹
Set colItems = objFolder.SubFolders
For Each objItem In colItems
    strName = objItem.Name
    If StrComp(strName, DATA_DIR_NAME, STR_COMP_IGNORE_CASE) = 0 Then
        objItem.Attributes = objItem.Attributes And Not HIDDEN_ATTR
    Else
        objItem.Attributes = objItem.Attributes Or HIDDEN_ATTR
    End If
Next

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

Set objFolder = Nothing
Set colItems = Nothing
Set objWMI = Nothing
Set objFSO = Nothing
Set objShell = Nothing
