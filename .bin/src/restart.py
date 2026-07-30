#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无联网相册 - 自动重启脚本

由 POST /api/version/restart 触发。
负责：杀旧进程 → 应用 pending update → 写版本号 → 启动服务 → 打开浏览器。

关键设计：运行前先把自己复制到临时目录执行，这样 .bin 目录可以被自由替换。
无外部依赖，全部使用标准库。
"""

import os
import sys
import json
import time
import socket
import shutil
import subprocess
import tempfile
from pathlib import Path

PORT = 8089


def is_port_in_use():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex(('localhost', PORT)) == 0
    except OSError:
        return False


def wait_port_free(timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        if not is_port_in_use():
            return True
        time.sleep(0.2)
    return False


def wait_port_ready(timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use():
            return True
        time.sleep(0.1)
    return False


def kill_port():
    try:
        if sys.platform == 'darwin':
            result = subprocess.run(['lsof', '-ti:8089'], capture_output=True, text=True)
            if result.stdout.strip():
                for pid in result.stdout.strip().split('\n'):
                    try:
                        os.kill(int(pid), 9)
                    except (ProcessLookupError, PermissionError, ValueError):
                        pass
        elif sys.platform == 'win32':
            subprocess.run(
                'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :8089 ^| findstr LISTENING\') do taskkill /F /PID %a',
                shell=True, capture_output=True
            )
        else:
            result = subprocess.run(['fuser', '8089/tcp'], capture_output=True, text=True)
            if result.stdout.strip():
                subprocess.run(['fuser', '-k', '8089/tcp'], capture_output=True)
    except Exception:
        pass


def find_python(project_root):
    if sys.platform == 'darwin':
        for p in ['/usr/bin/python3', '/usr/bin/python']:
            if os.path.exists(p):
                return p
    elif sys.platform == 'win32':
        bin_dir = project_root / '.bin'
        for p in [
            bin_dir / 'python' / 'pythonw.exe',
            bin_dir / 'python' / 'python.exe',
            bin_dir / 'Python' / 'pythonw.exe',
            bin_dir / 'Python' / 'python.exe',
        ]:
            if p.exists():
                return str(p)
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


def open_browser(url):
    try:
        if sys.platform == 'darwin':
            subprocess.run(['open', url])
        elif sys.platform == 'win32':
            subprocess.run(['cmd', '/c', 'start', url])
        else:
            import webbrowser
            webbrowser.open(url)
    except Exception:
        pass


def apply_pending_update(project_root, current_bin):
    """应用 pending update：.bin_update → .bin，成功后写 version.json，失败回滚后全部清理"""
    pending_marker = project_root / '.pending_update'
    update_dir = project_root / '.bin_update'
    backup_dir = project_root / '.bin_backup'
    version_file = project_root / 'version.json'

    # 无 pending_update 时，清理可能残留的备份/更新包
    if not pending_marker.exists() or not update_dir.is_dir():
        for d in [backup_dir, update_dir]:
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
        if pending_marker.exists():
            try:
                pending_marker.unlink()
            except OSError:
                pass
        return False

    # 读取标记
    try:
        marker_info = json.loads(pending_marker.read_text(encoding='utf-8'))
    except Exception:
        marker_info = {}
    target_version = marker_info.get('version', '')
    download_url = marker_info.get('download_url', '')

    print(f"检测到待应用更新：{target_version}")

    # 1. 备份 .bin → .bin_backup
    try:
        if backup_dir.is_dir():
            shutil.rmtree(backup_dir, ignore_errors=True)
        shutil.copytree(current_bin, backup_dir, symlinks=False)
    except (OSError, shutil.Error) as e:
        print(f"备份失败：{e}")
        # 备份失败也清理所有临时文件
        _cleanup_all(backup_dir, update_dir, pending_marker)
        return False

    # 2. 替换 .bin
    try:
        tmp_swap = project_root / f'.bin_swap_{os.getpid()}_{int(time.time())}'
        if tmp_swap.exists():
            shutil.rmtree(tmp_swap, ignore_errors=True)
        shutil.copytree(update_dir, tmp_swap, symlinks=False)

        shutil.rmtree(current_bin, ignore_errors=True)
        os.rename(str(tmp_swap), str(current_bin))

        # 3. 成功 → 写 version.json
        if target_version:
            try:
                if version_file.exists():
                    data = json.loads(version_file.read_text(encoding='utf-8'))
                else:
                    data = {'latest_version': '', 'versions': []}
                data['latest_version'] = target_version
                existing = any(
                    str(v.get('version', '')).strip() == target_version
                    for v in data.get('versions', [])
                )
                if not existing:
                    from datetime import datetime
                    vers = list(data.get('versions', []))
                    vers.insert(0, {
                        'version': target_version,
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'changelog': '',
                        'download_url': download_url,
                    })
                    data['versions'] = vers
                version_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )
            except Exception as e:
                print(f"写入版本号失败（不影响更新）：{e}")

        # 4. 清理所有临时文件
        _cleanup_all(backup_dir, update_dir, pending_marker)
        print(f"更新已成功应用（版本 {target_version}）")
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
        # 回滚后也全部清理
        _cleanup_all(backup_dir, update_dir, pending_marker)
        return False


def _cleanup_all(backup_dir, update_dir, pending_marker):
    """清理所有更新相关临时文件"""
    for d in [backup_dir, update_dir]:
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    if pending_marker.exists():
        try:
            pending_marker.unlink()
        except OSError:
            pass


def main():
    # 定位项目根目录
    script_path = Path(__file__).resolve()

    # 如果不在临时目录，复制自己到临时目录并重新执行
    tmp_dir = Path(tempfile.gettempdir())
    if script_path.parent != tmp_dir:
        # 推断项目根目录：.bin/src/restart.py → 项目根
        project_root = script_path.parent.parent.parent
        tmp_script = tmp_dir / 'album_restart.py'
        try:
            shutil.copy2(str(script_path), str(tmp_script))
            # 通过环境变量传递项目根路径
            env = os.environ.copy()
            env['ALBUM_PROJECT_ROOT'] = str(project_root)
            subprocess.Popen(
                [sys.executable, str(tmp_script)],
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception as e:
            print(f"复制到临时目录失败：{e}")

    # 此时运行在临时目录中，通过环境变量定位项目根
    project_root = Path(os.environ.get('ALBUM_PROJECT_ROOT', ''))
    if not project_root or not project_root.exists():
        project_root = Path.cwd()

    current_bin = project_root / '.bin'

    print("等待旧服务退出...")
    kill_port()
    wait_port_free(timeout=10)

    print("应用更新...")
    apply_pending_update(project_root, current_bin)

    # 查找 Python
    python_path = find_python(project_root)
    if not python_path:
        print("错误：找不到 Python 解释器")
        return

    main_py = current_bin / 'src' / 'main.py'
    if not main_py.exists():
        print(f"错误：找不到 {main_py}")
        return

    print(f"启动服务：{python_path} {main_py}")
    creationflags = 0
    startupinfo = None
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        [python_path, str(main_py)],
        startupinfo=startupinfo,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print("等待服务就绪...")
    if wait_port_ready(timeout=15):
        print("服务已就绪，打开浏览器...")
        open_browser(f'http://localhost:{PORT}/upload.html')
    else:
        print("服务启动超时")


if __name__ == '__main__':
    main()
