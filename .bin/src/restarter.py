#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无联网相册 - 自动重启 & 应用更新脚本
独立运行（脱离父 HTTP 服务进程），负责：

1) 读取 .pending_update 标记（含目标版本号）
2) 关闭当前监听 8089 端口的服务
3) 原子替换 .bin_update → .bin（失败自动回滚，回滚成功删 .bin_backup）
4) 仅在替换成功后：更新 version.json.latest_version
5) 重新启动服务、等待就绪
6) 打开浏览器跳回 /upload.html（不是首页）

用法：
    python restarter.py
触发时机：
    上传页点击「更新到此版本」→ 下载完成 → 倒计时结束 → POST /api/version/restart
"""

import json
import os
import sys
import time
import socket
import shutil
import subprocess
import urllib.request
import webbrowser
from pathlib import Path


# ====== 常量（与 config.py/launcher.py 保持一致，避免 import 带来的路径耦合） ======
PORT = 8089
SERVER_READY_MAX_WAIT = 12  # 秒，服务重启就绪最大等待
PORT_RELEASE_MAX_WAIT = 4   # 秒，kill 后端口释放最大等待
VERSION_JSON_NAME = 'version.json'


# ====== 日志（简单 stdout/stderr，调用方 Popen 已重定向到 .user_data/restarter.log） ======
def log(msg: str) -> None:
    ts = time.strftime('%H:%M:%S')
    print(f"[restarter {ts}] {msg}", flush=True)


def err(msg: str) -> None:
    ts = time.strftime('%H:%M:%S')
    print(f"[restarter {ts}] ERROR: {msg}", file=sys.stderr, flush=True)


# ====== 路径解析 ======
def resolve_project_root() -> Path:
    """确定项目根目录（.bin 的父目录）。

    优先级：
    1) cwd 若包含 .bin/src/main.py 直接用
    2) 通过 __file__ 相对定位：.bin/src/restarter.py → .bin → 父目录
    3) QORDER_BASE_DIR 环境变量兜底
    """
    cwd = Path(os.getcwd()).resolve()
    if (cwd / '.bin' / 'src' / 'main.py').is_file():
        return cwd
    here = Path(__file__).resolve()  # .bin/src/restarter.py
    candidate = here.parent.parent.parent  # .bin → project_root
    if (candidate / '.bin' / 'src' / 'main.py').is_file():
        return candidate
    env_base = os.environ.get('QORDER_BASE_DIR')
    if env_base:
        p = Path(env_base).resolve()
        if (p / '.bin' / 'src' / 'main.py').is_file():
            return p
    # 兜底：用 cwd（即使不完美也先继续）
    return cwd


def is_port_in_use() -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex(('127.0.0.1', PORT)) == 0
    except OSError:
        return False


def wait_port_free(timeout: float = PORT_RELEASE_MAX_WAIT) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if not is_port_in_use():
            return True
        time.sleep(0.15)
    return not is_port_in_use()


def is_server_ready() -> bool:
    """通过 /api/summary 检查服务是否真的启动成功"""
    try:
        req = urllib.request.Request(
            f'http://127.0.0.1:{PORT}/api/summary',
            headers={'User-Agent': 'RestarterProbe'},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_server_ready(timeout: float = SERVER_READY_MAX_WAIT) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if is_server_ready():
            return True
        time.sleep(0.2)
    return is_server_ready()


# ====== 进程终止 ======
def kill_listeners_on_port() -> None:
    """终止所有占用 8089 端口的进程（跨平台）。"""
    if sys.platform == 'darwin':
        try:
            r = subprocess.run(
                ['lsof', '-ti:%d' % PORT],
                capture_output=True, text=True, timeout=5,
            )
            for pid in (r.stdout or '').strip().splitlines():
                pid = pid.strip()
                if not pid:
                    continue
                try:
                    os.kill(int(pid), 9)
                    log(f"已终止占用端口进程 PID={pid}")
                except (ProcessLookupError, ValueError, PermissionError) as ex:
                    err(f"终止进程失败 PID={pid}: {ex}")
        except Exception as ex:
            err(f"lsof 扫描失败: {ex}")
    elif sys.platform.startswith('linux'):
        try:
            subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True, timeout=5)
        except Exception as ex:
            err(f"fuser 终止失败: {ex}")
    elif sys.platform == 'win32':
        try:
            r = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True, text=True, timeout=5,
            )
            for line in (r.stdout or '').splitlines():
                if f':{PORT}' in line and 'LISTENING' in line:
                    parts = line.split()
                    if parts:
                        pid = parts[-1].strip()
                        try:
                            subprocess.run(
                                ['taskkill', '/F', '/PID', pid],
                                capture_output=True, timeout=5,
                            )
                            log(f"已终止占用端口进程 PID={pid}")
                        except Exception as ex:
                            err(f"taskkill 失败 PID={pid}: {ex}")
            # 兜底：按命令行模式匹配 main.py
            try:
                r2 = subprocess.run(
                    ['wmic', 'process', 'where',
                     "CommandLine LIKE '%main.py%'",
                     'get', 'ProcessId'],
                    capture_output=True, text=True, timeout=5,
                )
                for line in (r2.stdout or '').splitlines()[1:]:
                    pid = line.strip()
                    if pid.isdigit():
                        try:
                            subprocess.run(
                                ['taskkill', '/F', '/PID', pid],
                                capture_output=True, timeout=5,
                            )
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception as ex:
            err(f"Windows 进程清理失败: {ex}")


# ====== Python 解释器查找 ======
def find_python_executable(project_root: Path) -> str:
    bin_dir = project_root / '.bin'
    if sys.platform == 'win32':
        for name in ['pythonw.exe', 'python.exe']:
            p = bin_dir / 'python' / name
            if p.is_file():
                return str(p)
    # macOS: 优先系统 python3（与双击启动脚本一致）
    if sys.platform == 'darwin':
        for p in ['/usr/bin/python3', '/usr/bin/python']:
            if Path(p).is_file():
                return p
    # 回退当前解释器
    return sys.executable or 'python3'


# ====== 主流程 ======
def apply_update(project_root: Path) -> tuple[bool, str]:
    """应用 .bin_update → .bin。

    Returns:
        (succeeded, message)
    """
    pending_marker = project_root / '.pending_update'
    update_dir = project_root / '.bin_update'
    bin_dir = project_root / '.bin'
    backup_dir = project_root / '.bin_backup'
    version_file = project_root / VERSION_JSON_NAME

    # 1) 读取标记
    target_version = ''
    try:
        if pending_marker.is_file():
            info = json.loads(pending_marker.read_text(encoding='utf-8'))
            target_version = str(info.get('version', '') or '').strip()
    except Exception as ex:
        err(f"读取 .pending_update 失败: {ex}")

    # 2) 清理旧备份（若存在），防止 mv 失败
    if backup_dir.exists():
        try:
            shutil.rmtree(backup_dir, ignore_errors=True)
            log("已清理旧的 .bin_backup")
        except Exception as ex:
            err(f"清理 .bin_backup 失败: {ex}")
            # 继续尝试，因为即使有残留也可能由后续 mv 覆盖

    has_update = update_dir.is_dir() and pending_marker.is_file()

    if has_update:
        log(f"检测到待应用更新（目标版本 {target_version or '未知'}），开始替换 .bin ...")

        # 3) 备份当前 .bin
        backup_ok = True
        if bin_dir.exists():
            try:
                bin_dir.rename(backup_dir)
                log(f"已备份当前 .bin → .bin_backup")
            except Exception as ex:
                err(f"备份 .bin 失败: {ex}")
                backup_ok = False
                # Windows 有时因句柄占用 rename 失败，尝试 rmtree + copytree
                try:
                    log("尝试使用复制作为兜底...")
                    if backup_dir.exists():
                        shutil.rmtree(backup_dir, ignore_errors=True)
                    shutil.copytree(bin_dir, backup_dir, symlinks=False)
                    backup_ok = True
                    log("复制备份成功")
                except Exception as ex2:
                    err(f"复制备份也失败: {ex2}")

        # 4) 用 .bin_update 替换当前 .bin
        replace_ok = False
        if backup_ok:
            try:
                # 先清掉原来的 bin（如果 rename 兜底没清）
                if bin_dir.exists():
                    shutil.rmtree(bin_dir, ignore_errors=True)
                update_dir.rename(bin_dir)
                replace_ok = True
                log("已应用 .bin_update → .bin")
            except Exception as ex:
                err(f"mv .bin_update → .bin 失败: {ex}")
                # 再兜底：copytree
                try:
                    if bin_dir.exists():
                        shutil.rmtree(bin_dir, ignore_errors=True)
                    shutil.copytree(update_dir, bin_dir, symlinks=False)
                    replace_ok = True
                    log("复制替换 .bin_update → .bin 成功")
                except Exception as ex2:
                    err(f"复制替换也失败: {ex2}")

        # 5) 替换失败 → 回滚
        rollback_done = False
        if not replace_ok:
            err("更新替换失败，启动回滚流程...")
            if backup_dir.exists():
                try:
                    if bin_dir.exists():
                        shutil.rmtree(bin_dir, ignore_errors=True)
                    backup_dir.rename(bin_dir)
                    rollback_done = True
                    log("回滚成功：.bin_backup → .bin")
                except Exception as ex:
                    err(f"mv 回滚失败: {ex}")
                    try:
                        shutil.copytree(backup_dir, bin_dir, symlinks=False)
                        rollback_done = True
                        log("复制回滚成功")
                    except Exception as ex2:
                        err(f"复制回滚也失败: {ex2}")

            # 回滚成功后：务必删除 .bin_backup
            if rollback_done and backup_dir.exists():
                try:
                    shutil.rmtree(backup_dir, ignore_errors=True)
                    log("回滚成功后已删除 .bin_backup")
                except Exception as ex:
                    err(f"删除 .bin_backup 失败: {ex}")

            # 清除 .pending_update 和残留 .bin_update
            try:
                if pending_marker.exists():
                    pending_marker.unlink()
                if update_dir.exists():
                    shutil.rmtree(update_dir, ignore_errors=True)
            except Exception:
                pass
            return False, (
                '更新替换失败，已自动回滚到旧版本。'
                '若问题反复出现，请手动备份后重新下载更新包。'
            )

        # 6) 替换成功：写入 version.json.latest_version（关键点：只在成功后写）
        if target_version:
            try:
                if version_file.is_file():
                    data = json.loads(version_file.read_text(encoding='utf-8'))
                else:
                    data = {'latest_version': '', 'versions': []}
                if str(data.get('latest_version', '')) != target_version:
                    data['latest_version'] = target_version
                    version_file.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding='utf-8',
                    )
                    log(f"version.json.latest_version 已更新为 {target_version}")
            except Exception as ex:
                err(f"写入 version.json 失败（不影响功能）: {ex}")

        # 7) 清理：.pending_update / .bin_update（必删）、.bin_backup（可选，默认清理）
        try:
            if pending_marker.exists():
                pending_marker.unlink()
        except Exception:
            pass
        try:
            if update_dir.exists():
                shutil.rmtree(update_dir, ignore_errors=True)
        except Exception:
            pass
        try:
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
                log("更新成功后已清理 .bin_backup")
        except Exception:
            pass

        return True, f'已成功应用更新到版本 {target_version or "未知"}'

    else:
        # 没有更新包（可能纯重启）——什么也不做
        log("没有检测到待应用更新（.pending_update/.bin_update 不存在），仅执行重启。")
        # 安全起见，清理可能的标记文件
        try:
            if pending_marker.exists():
                pending_marker.unlink()
        except Exception:
            pass
        return True, '无更新，仅重启'


def start_server(project_root: Path) -> subprocess.Popen | None:
    """启动新的服务进程（后台脱离，不依赖当前 restarter 存活）。"""
    main_py = project_root / '.bin' / 'src' / 'main.py'
    python_exe = find_python_executable(project_root)
    log(f"使用 Python: {python_exe}")

    try:
        if sys.platform == 'win32':
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_NO_WINDOW = 0x08000000
            creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            return subprocess.Popen(
                [python_exe, str(main_py)],
                creationflags=creationflags,
                startupinfo=startupinfo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(project_root),
            )
        else:
            # macOS / Linux
            return subprocess.Popen(
                [python_exe, str(main_py)],
                start_new_session=True,
                preexec_fn=os.setpgrp,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(project_root),
            )
    except Exception as ex:
        err(f"启动服务进程失败: {ex}")
        return None


def open_upload_page() -> None:
    url = f'http://127.0.0.1:{PORT}/upload.html'
    try:
        if sys.platform == 'darwin':
            subprocess.Popen(['open', url])
        elif sys.platform == 'win32':
            webbrowser.open(url, new=2, autoraise=True)
        else:
            webbrowser.open(url, new=2, autoraise=True)
        log(f"已请求打开浏览器: {url}")
    except Exception as ex:
        err(f"打开浏览器失败: {ex}")


def main() -> int:
    log(f"====== restarter 启动 (pid={os.getpid()}, platform={sys.platform}) ======")
    project_root = resolve_project_root()
    log(f"项目根目录: {project_root}")

    # 1) kill 当前服务，释放端口
    log("清理端口 8089 上的旧进程...")
    kill_listeners_on_port()
    if not wait_port_free():
        err("端口 8089 长时间未释放，仍尝试继续（可能替换 .bin 失败）")
    else:
        log("端口 8089 已释放")

    # 2) 应用更新（含回滚逻辑）
    ok, msg = apply_update(project_root)
    log(f"应用更新结果: ok={ok} - {msg}")

    # 3) 启动新服务（即使更新回滚也要启动，保证用户能用）
    proc = start_server(project_root)
    if proc is None:
        err("无法启动服务，restarter 中止")
        return 2
    log(f"服务进程已启动 PID={proc.pid}，等待就绪...")

    # 4) 等待就绪
    if wait_server_ready():
        log("服务已就绪")
    else:
        err("服务长时间未就绪，仍尝试打开上传页（用户可手动刷新）")
        # 极端兜底：如果更新后新 .bin 损坏，尝试自动回滚重启一次
        backup_dir = project_root / '.bin_backup'
        pending_marker = project_root / '.pending_update'
        if pending_marker.exists() and backup_dir.exists():
            log("检测到可能的更新失败，尝试最后一次回滚重启...")
            try:
                kill_listeners_on_port()
                wait_port_free()
                bin_dir = project_root / '.bin'
                if bin_dir.exists():
                    shutil.rmtree(bin_dir, ignore_errors=True)
                backup_dir.rename(bin_dir)
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                # 清 marker
                try:
                    pending_marker.unlink()
                except Exception:
                    pass
                proc2 = start_server(project_root)
                if proc2 and wait_server_ready():
                    log("兜底回滚重启成功！")
                else:
                    err("兜底回滚也失败")
            except Exception as ex:
                err(f"兜底回滚异常: {ex}")

    # 5) 打开上传页（不是首页）
    open_upload_page()

    log("restarter 完成，退出。")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as _e:
        err(f"restarter 顶层异常: {_e}")
        sys.exit(99)
