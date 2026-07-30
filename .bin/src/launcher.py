#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无联网相册 - 启动器
检测端口 -> 启动服务 -> 等待就绪 -> 打开浏览器
"""

import os
import sys
import time
import json
import socket
import shutil
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


def try_apply_pending_update() -> bool:
    """如果存在待应用更新（.pending_update + .bin_update），则应用更新：
    1. 把 .bin → .bin_backup（备份旧版本）
    2. 把 .bin_update → .bin（应用新版本）
    3. 应用成功后删除 .bin_backup 和标记文件
    4. 失败时从 .bin_backup 回滚
    返回：有更新被应用时返回 True，供调用方决定是否需要二次重启
    """
    # launcher.py 在 <project_root>/.bin/src/launcher.py → project_root 是 Qorder/
    script_dir = Path(__file__).resolve().parent
    if script_dir.name == 'src':
        project_root = script_dir.parent.parent  # 项目根（Qorder/）
        current_bin = script_dir.parent     # .bin/
    else:
        # 防御路径：script_dir/.bin/ （若异常
        project_root = script_dir.parent
        current_bin = script_dir
    pending_marker = project_root / '.pending_update'
    update_dir = project_root / '.bin_update'
    backup_dir = project_root / '.bin_backup'

    # 没有待应用更新，直接返回
    if not pending_marker.exists() or not update_dir.is_dir():
        # 即便没有更新，也清理一下可能残留的旧备份（磁盘空间）
        if backup_dir.is_dir():
            shutil.rmtree(backup_dir, ignore_errors=True)
        return False

    # 读取标记（用于日志，失败不阻塞）
    try:
        marker_info = json.loads(pending_marker.read_text(encoding='utf-8')) if pending_marker.exists() else {}
    except Exception:
        marker_info = {}

    print(f"检测到待应用更新：{marker_info.get('version', '新版本')}")

    # 1. 清理旧备份（若存在）→ 2. 当前 .bin 备份为 .bin_backup
    try:
        if backup_dir.is_dir():
            shutil.rmtree(backup_dir, ignore_errors=True)
        shutil.copytree(current_bin, backup_dir, symlinks=False)
    except (OSError, shutil.Error) as e:
        print(f"更新失败（备份步骤）：{e}")
        # 备份失败不要阻塞启动，继续正常启动旧版本
        return False

    rollback_needed = True  # 默认需要回滚，只有全部成功后置 False
    try:
        # 2. 用 .bin_update 覆盖 .bin
        # 为了保证 launcher.py 也能被替换，先把 update_dir 内容复制到临时目录，再原子切换
        tmp_swap = project_root / f'.bin_swap_{os.getpid()}_{int(time.time())}'
        if tmp_swap.exists():
            shutil.rmtree(tmp_swap, ignore_errors=True)
        shutil.copytree(update_dir, tmp_swap, symlinks=False)

        # 删除旧的 .bin，把 tmp_swap 重命名为 .bin
        shutil.rmtree(current_bin, ignore_errors=True)
        os.rename(str(tmp_swap), str(current_bin))

        # 3. 应用成功，清理备份和更新包
        rollback_needed = False
        if backup_dir.is_dir():
            shutil.rmtree(backup_dir, ignore_errors=True)
        if update_dir.is_dir():
            shutil.rmtree(update_dir, ignore_errors=True)
        try:
            pending_marker.unlink()
        except OSError:
            pass

        print(f"更新已成功应用（版本 {marker_info.get('version', '新版本')}）")
        return True

    except (OSError, shutil.Error) as e:
        print(f"应用更新失败：{e}")
        # 回滚：.bin_backup → .bin
        try:
            if backup_dir.is_dir():
                if current_bin.exists():
                    shutil.rmtree(current_bin, ignore_errors=True)
                shutil.copytree(backup_dir, current_bin, symlinks=False)
                print("已回滚到旧版本")
        except Exception as rb_err:
            print(f"回滚失败：{rb_err}")
        return False
    finally:
        # 无论成功失败，保留备份文件夹直到下次启动前清理
        # 只有明确更新成功后，rollback_needed=False 已在上面删除 backup
        if rollback_needed:
            # 备份保留（.bin_backup），供手动排查 / 手动回滚，下次启动会清理
            pass


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
    # 第一步：如果有 pending_update，先应用更新（成功时 .bin_backup 会被清掉）
    # 注意：此步骤执行时 launcher.py 还在内存中，即便 .bin/src/launcher.py 被替换也不影响当前进程
    try:
        try_apply_pending_update()
    except Exception as e:
        print(f"应用更新时发生异常（继续正常启动）：{e}")

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

    # 启动服务进程 — 更新应用完成后 .bin/src/main.py 已是新版本，直接启动即可
    main_py = Path(__file__).resolve().parent / 'main.py'
    
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
