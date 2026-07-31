#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
程序重启/更新应用脚本
- 从启动脚本或 HTTP API trigger-restart 调用
- 若存在 .pending_update + .bin_update，则替换 .bin 目录后再启动服务
- 无论成功/失败，都会清理 .pending_update/.bin_update/.bin_backup 临时文件
- 被 HTTP API trigger 时，会先等 1.2s 让父进程把响应发送完
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# 单实例锁：避免 HTTP trigger 与启动脚本同时跑 restarter 造成冲突
_SINGLE_LOCK_FP = None


LOG_FILE = None
LOG_FP = None


def log(msg: str) -> None:
    ts = time.strftime('%H:%M:%S')
    line = f"[restarter {ts}] {msg}\n"
    sys.stdout.write(line)
    sys.stdout.flush()
    if LOG_FP is not None:
        try:
            LOG_FP.write(line)
            LOG_FP.flush()
        except Exception:
            pass


def err(msg: str) -> None:
    ts = time.strftime('%H:%M:%S')
    line = f"[restarter {ts}] [ERR] {msg}\n"
    sys.stderr.write(line)
    sys.stderr.flush()
    if LOG_FP is not None:
        try:
            LOG_FP.write(line)
            LOG_FP.flush()
        except Exception:
            pass


def cleanup_update_tempfiles(project_root: Path) -> None:
    """统一清理更新相关的临时文件/目录（success / rollback / 异常 都要走这里）"""
    pending_marker = project_root / '.pending_update'
    bin_update = project_root / '.bin_update'
    bin_backup = project_root / '.bin_backup'
    for label, path, kind in [
        ('.pending_update', pending_marker, 'file'),
        ('.bin_update', bin_update, 'dir'),
        ('.bin_backup', bin_backup, 'dir'),
    ]:
        if not path.exists():
            continue
        try:
            if kind == 'file':
                path.unlink()
            else:
                shutil.rmtree(path, ignore_errors=True)
            log(f"cleanup: 已删除 {label}")
        except Exception as ex:
            err(f"cleanup: 删除 {label} 失败（忽略继续）: {ex}")


def resolve_project_root() -> Path:
    # restarter.py 位于 <PROJECT_ROOT>/.bin/src/restarter.py
    here = Path(__file__).resolve().parent
    if here.name != 'src':
        return here.parent.parent
    bin_dir = here.parent
    if bin_dir.name != '.bin':
        return bin_dir.parent
    return bin_dir.parent


def acquire_single_instance_lock(project_root: Path) -> bool:
    """单实例锁：同一时间只允许一个 restarter 在跑（macOS/Linux 用 fcntl；Windows 用文件占用）
    成功取得锁返回 True；已有 restarter 在跑返回 False（直接退出避免冲突）
    """
    global _SINGLE_LOCK_FP
    lock_file = project_root / '.user_data' / 'restarter.lock'
    try:
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        _SINGLE_LOCK_FP = open(lock_file, 'a+', encoding='utf-8')
        if sys.platform.startswith('win'):
            # Windows：尝试独占重命名，失败则视为已有进程
            try:
                probe = project_root / '.user_data' / 'restarter.lock.probe'
                os.replace(str(lock_file), str(probe))
                os.replace(str(probe), str(lock_file))
            except OSError:
                try:
                    _SINGLE_LOCK_FP.close()
                except Exception:
                    pass
                _SINGLE_LOCK_FP = None
                return False
            return True
        # macOS / Linux
        import fcntl
        try:
            fcntl.flock(_SINGLE_LOCK_FP.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, ImportError):
            try:
                _SINGLE_LOCK_FP.close()
            except Exception:
                pass
            _SINGLE_LOCK_FP = None
            return False
        try:
            _SINGLE_LOCK_FP.truncate(0)
            _SINGLE_LOCK_FP.seek(0)
            _SINGLE_LOCK_FP.write(f"pid={os.getpid()}\n")
            _SINGLE_LOCK_FP.flush()
        except Exception:
            pass
        return True
    except Exception:
        try:
            if _SINGLE_LOCK_FP is not None:
                _SINGLE_LOCK_FP.close()
        except Exception:
            pass
        _SINGLE_LOCK_FP = None
        # 无法创建锁也不阻塞启动（极端 fallback）
        return True


def apply_update(project_root: Path) -> dict:
    """存在待应用更新则替换 .bin，返回 {'ok': bool, 'applied': bool, 'message': str}"""
    pending_marker = project_root / '.pending_update'
    bin_update = project_root / '.bin_update'
    bin_dir = project_root / '.bin'
    bin_backup = project_root / '.bin_backup'

    result = {'ok': True, 'applied': False, 'message': ''}

    has_marker = pending_marker.exists() and pending_marker.is_file()
    has_update = bin_update.is_dir() and (bin_update / 'src' / 'main.py').exists()

    if not has_marker and not has_update:
        return result

    if has_marker and not has_update:
        # 标记残留但无实际更新目录 → 清掉标记后继续
        log(f"检测到 .pending_update 但 .bin_update 不存在或不合法，清除标记继续启动")
        cleanup_update_tempfiles(project_root)
        return result

    if has_update and not has_marker:
        # 下载目录残留但无标记，清理后启动
        log(f"检测到 .bin_update 但 .pending_update 不存在，清除残留后启动")
        cleanup_update_tempfiles(project_root)
        return result

    # 读取标记中的目标版本
    target_version = ''
    try:
        info = json.loads(pending_marker.read_text(encoding='utf-8'))
        target_version = str(info.get('version', '') or '').strip()
    except Exception:
        target_version = ''

    if not target_version:
        log(f".pending_update 中未找到有效 target_version，清除残留后启动")
        cleanup_update_tempfiles(project_root)
        return result

    log(f"检测到待应用更新（目标版本 {target_version}），开始替换 .bin ...")

    try:
        # 1) 备份当前 .bin
        if bin_dir.exists():
            if bin_backup.exists():
                shutil.rmtree(bin_backup, ignore_errors=True)
            shutil.copytree(bin_dir, bin_backup, symlinks=False)
            log(f"已备份当前 .bin → .bin_backup")

        # 2) 用 .bin_update 替换 .bin
        if bin_dir.exists():
            shutil.rmtree(bin_dir, ignore_errors=True)
        shutil.copytree(bin_update, bin_dir, symlinks=False)
        log(f"已应用 .bin_update → .bin")

        # 3) 把 version.json.latest_version 再写一次（兜底）
        try:
            vfile = project_root / 'version.json'
            if vfile.exists():
                data = json.loads(vfile.read_text(encoding='utf-8'))
                data['latest_version'] = target_version
                vfile.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                log(f"version.json.latest_version 已更新为 {target_version}")
        except Exception:
            pass

        result['applied'] = True
        result['message'] = f"已成功应用更新到版本 {target_version}"
        cleanup_update_tempfiles(project_root)

    except Exception as ex:
        # 失败则尝试回滚
        result['ok'] = False
        result['applied'] = False
        msg = f"应用更新失败：{ex}"
        result['message'] = msg
        err(msg)

        # 回滚：把 .bin_backup 复制回 .bin
        try:
            if bin_backup.exists():
                if bin_dir.exists():
                    shutil.rmtree(bin_dir, ignore_errors=True)
                shutil.copytree(bin_backup, bin_dir, symlinks=False)
                log(f"已从 .bin_backup 回滚到旧版本")
                result['message'] = f"应用更新失败，已回滚到旧版本: {ex}"
                cleanup_update_tempfiles(project_root)
        except Exception as rb:
            err(f"回滚失败：{rb}")
            result['message'] = f"应用更新失败，且回滚也失败: {ex} | rollback={rb}"

    return result


def kill_port_holders(port: int, project_root: Path) -> None:
    """释放占用端口的旧进程（只杀 python3 / restarter 相关，避免误伤）"""
    platform = sys.platform
    try:
        if platform == 'darwin':
            out = subprocess.check_output(
                ['lsof', '-ti', f':{port}'], stderr=subprocess.DEVNULL
            ).decode('utf-8', errors='ignore').strip()
            pids = [p for p in out.splitlines() if p.strip().isdigit()]
            for pid in pids:
                try:
                    subprocess.run(['kill', '-9', pid], stderr=subprocess.DEVNULL)
                    log(f"已终止占用端口进程 PID={pid}")
                except Exception:
                    pass
        elif platform.startswith('win'):
            out = subprocess.check_output(
                ['netstat', '-ano'], stderr=subprocess.DEVNULL
            ).decode('utf-8', errors='ignore')
            for line in out.splitlines():
                if f':{port} ' in line and 'LISTENING' in line:
                    parts = line.strip().split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit():
                            try:
                                subprocess.run(['taskkill', '/F', '/PID', pid], stderr=subprocess.DEVNULL)
                                log(f"已终止占用端口进程 PID={pid}")
                            except Exception:
                                pass
        else:
            # linux
            try:
                subprocess.run(['fuser', '-k', f'{port}/tcp'], stderr=subprocess.DEVNULL)
            except Exception:
                pass
    except Exception as ex:
        log(f"清理端口进程失败（忽略继续）: {ex}")

    # 兜底：按进程命令行查找 main.py / restarter.py
    try:
        if platform == 'darwin':
            out = subprocess.check_output(
                ['ps', '-Ao', 'pid=,command='], stderr=subprocess.DEVNULL
            ).decode('utf-8', errors='ignore')
            prj = str(project_root)
            self_pid = str(os.getpid())
            for line in out.splitlines():
                l = line.strip()
                if not l:
                    continue
                idx = l.find(' ')
                if idx <= 0:
                    continue
                pid = l[:idx].strip()
                if pid == self_pid:
                    # 跳过自己，避免自杀
                    continue
                cmd = l[idx + 1:]
                if ('.bin/src/main.py' in cmd or '.bin/src/restarter.py' in cmd) and prj in cmd:
                    if not pid.isdigit():
                        continue
                    try:
                        subprocess.run(['kill', '-9', pid], stderr=subprocess.DEVNULL)
                        log(f"已终止旧进程 PID={pid} ({cmd[:70]})")
                    except Exception:
                        pass
    except Exception:
        pass


def wait_port_ready(port: int, timeout: float = 15.0) -> bool:
    import socket
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.create_connection(('127.0.0.1', port), timeout=0.5)
            s.close()
            return True
        except Exception:
            time.sleep(0.2)
    return False


def start_server(project_root: Path, port: int) -> int:
    python_bin = sys.executable
    main_py = project_root / '.bin' / 'src' / 'main.py'
    log(f"使用 Python: {python_bin}")

    # macOS 用 nohup 后台运行；Windows 用 DETACHED_PROCESS
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    if sys.platform == 'darwin':
        log_path = '/tmp/album_viewer.log'
        with open(log_path, 'ab') as f:
            proc = subprocess.Popen(
                ['nohup', python_bin, str(main_py)],
                cwd=str(project_root),
                stdout=f,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
    elif sys.platform.startswith('win'):
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        log_path = project_root / '.user_data' / 'server.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fp = open(log_path, 'ab')
        proc = subprocess.Popen(
            [python_bin, str(main_py)],
            cwd=str(project_root),
            stdout=fp,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        )
    else:
        # linux
        log_path = '/tmp/album_viewer.log'
        with open(log_path, 'ab') as f:
            proc = subprocess.Popen(
                ['nohup', python_bin, str(main_py)],
                cwd=str(project_root),
                stdout=f,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )

    log(f"服务进程已启动 PID={proc.pid}，等待就绪...")
    time.sleep(0.6)
    if wait_port_ready(port, timeout=15.0):
        log(f"服务已就绪")
    else:
        log(f"警告：等待 {port} 端口超时，但已启动进程，可能稍后就绪")

    # 打开浏览器（mac 用 open，win 用 start）
    try:
        url = f"http://127.0.0.1:{port}/upload.html"
        if sys.platform == 'darwin':
            subprocess.Popen(['open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith('win'):
            os.startfile(url)  # noqa
        log(f"已请求打开浏览器: {url}")
    except Exception as ex:
        log(f"自动打开浏览器失败（忽略）: {ex}")

    return proc.pid


def main() -> int:
    global LOG_FP, LOG_FILE

    project_root = resolve_project_root()
    user_data = project_root / '.user_data'
    user_data.mkdir(parents=True, exist_ok=True)
    LOG_FILE = user_data / 'restarter.log'
    try:
        LOG_FP = open(LOG_FILE, 'a', encoding='utf-8')
    except Exception:
        LOG_FP = None

    started_ts = int(time.time())
    print(f"\n=== restarter 启动 ts={started_ts} ===")
    log(f"====== restarter 启动 (pid={os.getpid()}, platform={sys.platform}) ======")
    log(f"项目根目录: {project_root}")

    # 单实例锁：防止 HTTP trigger + 启动脚本并发导致的冲突（拿不到锁直接退出）
    if not acquire_single_instance_lock(project_root):
        log(f"检测到另一个 restarter 进程正在运行，本次退出避免冲突")
        try:
            if LOG_FP is not None:
                LOG_FP.close()
        except Exception:
            pass
        return 0

    # 解析参数
    # 支持:  restarter.py [--delay-before-kill SEC] [--port PORT] [--kill-parent PID]
    args = sys.argv[1:]
    delay_before_kill = 1.2
    port = 8089
    kill_parent_pid = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--delay-before-kill' and i + 1 < len(args):
            try:
                delay_before_kill = float(args[i + 1])
            except Exception:
                pass
            i += 2
        elif a == '--port' and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except Exception:
                pass
            i += 2
        elif a == '--kill-parent' and i + 1 < len(args):
            try:
                kill_parent_pid = int(args[i + 1])
            except Exception:
                pass
            i += 2
        else:
            i += 1

    # 启动前先把标记残留清掉（在 HTTP trigger 路径下，父进程会先调用 kill 自己，
    #  但这里我们先确保在 apply_update 前的异常路径也会 cleanup 干净）
    # 注意：不提前清，只 apply_update 会自动清；这里仅兜底：当 marker 存在但 bin_update 不存在时
    # apply_update 里已经做了

    try:
        # 被 HTTP trigger 时：延迟一段时间让父进程把 HTTP 响应发完、再清理端口
        if kill_parent_pid is not None or delay_before_kill > 0:
            log(f"等待 {delay_before_kill:.1f}s 让父进程把 HTTP 响应发送完毕...")
            time.sleep(delay_before_kill)

        # 杀父进程（HTTP API trigger 时传入），避免旧服务占用端口
        if kill_parent_pid is not None:
            try:
                if sys.platform.startswith('win'):
                    subprocess.run(['taskkill', '/F', '/PID', str(kill_parent_pid)],
                                   stderr=subprocess.DEVNULL)
                else:
                    subprocess.run(['kill', '-9', str(kill_parent_pid)],
                                   stderr=subprocess.DEVNULL)
                log(f"已终止父进程 PID={kill_parent_pid}")
                time.sleep(0.4)
            except Exception as ex:
                log(f"终止父进程失败（忽略）: {ex}")

        # 清理端口占用
        log(f"清理端口 {port} 上的旧进程...")
        kill_port_holders(port, project_root)
        time.sleep(0.3)
        log(f"端口 {port} 已释放")

        # 应用更新
        update_result = apply_update(project_root)
        log(f"应用更新结果: ok={update_result['ok']} - {update_result['message'] or '无待应用更新'}")
        if not update_result['ok']:
            err(f"应用更新失败: {update_result['message']}")

        # 启动服务
        start_server(project_root, port)

    except Exception as ex:
        err(f"restarter 异常: {ex}")
        # 异常情况下也要清临时文件，避免卡壳
        try:
            cleanup_update_tempfiles(project_root)
        except Exception:
            pass
        return 1
    finally:
        if LOG_FP is not None:
            try:
                LOG_FP.close()
            except Exception:
                pass
    log(f"restarter 完成，退出。")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
