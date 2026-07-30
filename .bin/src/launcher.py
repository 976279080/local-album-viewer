#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无联网相册 - 启动器
检测端口 -> 启动服务 -> 等待就绪 -> 打开浏览器
"""

import os
import sys
import time
import socket
import subprocess
import webbrowser
from pathlib import Path

PORT = 8089
MAX_WAIT = 8  # 最多等待8秒


def is_port_in_use():
    """检测端口是否已被占用（超时 0.3 秒足够）"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            result = s.connect_ex(('localhost', PORT))
            return result == 0
    except OSError:
        return False


def kill_port():
    """仅在端口被占用时才清理，减少无意义等待"""
    if not is_port_in_use():
        return
    try:
        if sys.platform == 'darwin':
            result = subprocess.run(['lsof', '-ti:8089'], capture_output=True, text=True)
            if result.stdout.strip():
                for pid in result.stdout.strip().split('\n'):
                    try:
                        os.kill(int(pid), 9)
                    except (ProcessLookupError, PermissionError, ValueError):
                        pass
                # 快速等待端口释放，最多 2 秒
                for _ in range(10):
                    time.sleep(0.2)
                    if not is_port_in_use():
                        break
        elif sys.platform == 'linux':
            result = subprocess.run(['fuser', '8089/tcp'], capture_output=True, text=True)
            if result.stdout.strip():
                subprocess.run(['fuser', '-k', '8089/tcp'], capture_output=True)
                time.sleep(0.5)
        else:  # Windows
            result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if ':8089' in line and 'LISTENING' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        try:
                            subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
                        except (subprocess.SubprocessError, FileNotFoundError):
                            pass
            time.sleep(0.5)
    except Exception as e:
        print(f"清理端口失败: {e}", file=sys.stderr)


def open_browser(url):
    """打开浏览器（使用默认浏览器）"""
    if sys.platform == 'darwin':
        subprocess.run(['open', url])
    elif sys.platform == 'win32':
        webbrowser.open(url)
    else:
        webbrowser.open(url)


def wait_for_server(timeout=MAX_WAIT):
    """等待服务就绪（每 0.05 秒轮询一次）"""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use():
            return True
        time.sleep(0.05)
    return False


def find_python():
    """查找可用的 Python 解释器
    
    跨平台路径支持：
    - Mac: /usr/bin/python3 (系统 Python)
    - Windows: bin/python/python.exe (portable Python)
    """
    # 获取项目根目录（无联网相册_mac.app 的父目录）
    script_dir = Path(__file__).parent
    bin_dir = script_dir.parent
    
    if sys.platform == 'darwin':
        # macOS 路径优先级 - 优先使用系统 Python（所有 macOS 10.15+ 都自带）
        mac_paths = [
            '/usr/bin/python3',
            '/usr/bin/python',
        ]
        for p in mac_paths:
            if os.path.exists(p):
                return p
    
    elif sys.platform == 'win32':
        # Windows 路径优先级 - 优先 pythonw.exe（无窗口）
        win_paths = [
            bin_dir / 'python' / 'pythonw.exe',
            bin_dir / 'python' / 'python.exe',
            bin_dir / 'Python' / 'pythonw.exe',
            bin_dir / 'Python' / 'python.exe',
        ]
        for p in win_paths:
            if p.exists():
                return str(p)
    
    # 回退到系统 Python
    for name in ['python3', 'python']:
        try:
            result = subprocess.run(
                ['which', name] if sys.platform != 'win32' else ['where', name],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if os.path.exists(path):
                    return path
        except Exception:
            pass
    
    return None


def main():
    """主函数"""
    # 强制终止现有进程并清理端口
    print("检查并清理端口...")
    kill_port()
    
    # 查找 Python
    python_path = find_python()
    if not python_path:
        print("错误: 找不到可用的 Python 解释器")
        print("请检查:")
        if sys.platform == 'darwin':
            print("  - macOS 系统自带 Python: /usr/bin/python3")
            print("  - 确保安装了 Xcode Command Line Tools")
        elif sys.platform == 'win32':
            print("  - bin/python/python.exe")
        else:
            print("  - 系统 Python: python3")
        input("按回车键退出...")
        sys.exit(1)
    
    print(f"使用 Python: {python_path}")
    
    # 启动服务进程
    main_py = Path(__file__).parent / 'main.py'
    
    # 启动参数
    startupinfo = None
    creationflags = 0
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW
    
    # 使用 pythonw.exe (Windows无窗口) 或普通 python
    process = subprocess.Popen(
        [python_path, str(main_py)],
        startupinfo=startupinfo,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    print(f"正在启动服务 (PID: {process.pid})...")
    
    # 等待服务就绪（端口可用即视为就绪）
    if wait_for_server():
        print(f"服务已就绪，立即打开浏览器...")
        open_browser(f'http://localhost:{PORT}')
    else:
        print(f"服务启动超时，请检查日志")
        process.terminate()
        sys.exit(1)


if __name__ == '__main__':
    main()
