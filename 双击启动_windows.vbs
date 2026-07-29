' 无联网相册 - Windows 启动脚本
' 每次点击都重启服务，轮询端口后打开浏览器

Dim objShell, objFSO, objWMI, strBasePath, strPythonPath, strMainPath
Dim strCmd, intReturn, i, bReady

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' 获取脚本所在目录
strBasePath = objFSO.GetParentFolderName(WScript.ScriptFullName)

' main.py 路径
strMainPath = strBasePath & "\.bin\src\main.py"

' 检查 main.py 是否存在
If Not objFSO.FileExists(strMainPath) Then
    MsgBox "找不到 main.py！" & vbCrLf & _
           "请确保 .bin\src\main.py 存在", vbCritical, "错误"
    WScript.Quit 1
End If

' 优先使用 pythonw.exe（无窗口），其次 python.exe
strPythonPath = strBasePath & "\.bin\python\pythonw.exe"
If Not objFSO.FileExists(strPythonPath) Then
    strPythonPath = strBasePath & "\.bin\python\python.exe"
    If Not objFSO.FileExists(strPythonPath) Then
        MsgBox "找不到内嵌 Python 解释器！" & vbCrLf & _
               "请将 Python 放入 .bin\python\ 目录", vbCritical, "错误"
        WScript.Quit 1
    End If
End If

' 隐藏不需要用户看到的文件/文件夹
On Error Resume Next
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.bin""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.user_data""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\.trae""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\version.json""", 0, True
objShell.Run "cmd /c attrib +h """ & strBasePath & "\tests""", 0, True
On Error GoTo 0

' 每次点击都重启服务：先杀掉占用 8089 端口的旧进程
On Error Resume Next
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")
Dim colProcesses, objProcess
Set colProcesses = objWMI.ExecQuery _
    ("SELECT * FROM Win32_Process WHERE CommandLine LIKE '%main.py%' AND CommandLine LIKE '%Qorder%'")
For Each objProcess In colProcesses
    objProcess.Terminate
Next
WScript.Sleep 300
On Error GoTo 0

' 构建命令行 - 直接启动 main.py
strCmd = """" & strPythonPath & """ """ & strMainPath & """"

' 静默启动（窗口模式 = 0 隐藏，等待 = False 不等待）
intReturn = objShell.Run(strCmd, 0, False)

' 轮询端口（每200ms检查一次，最多等10秒）
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

' 打开浏览器
If bReady Then
    objShell.Run "cmd /c start http://localhost:8089"
Else
    MsgBox "服务启动超时，请检查日志", vbExclamation, "提示"
End If

Set objFSO = Nothing
Set objShell = Nothing
