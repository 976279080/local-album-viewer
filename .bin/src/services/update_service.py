"""更新包服务：集中处理下载、写标记、清理残留、触发重启的准备动作
与 version_service 解耦：
- version_service 只负责「读 version.json / 从 Gitee 拉远程版本列表」
- update_service 只负责「下载更新包 → 解压校验 → 写 .pending_update → 清理残留」
- 对外仅暴露两个方法：download_update / cleanup_tempfiles
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict

# 优先复用 config.py 的 BASE_DIR（与运行时保持一致），导入失败才 fallback
try:
    from config import BASE_DIR as _CFG_BASE_DIR
    BASE_DIR = _CFG_BASE_DIR
except Exception:
    BASE_DIR = Path(__file__).resolve().parent.parent

VERSION_JSON_PATH = 'version.json'

__all__ = ['UpdateService']


class UpdateService:
    """更新包下载与准备服务

    职责（单一）：
      1. 从 Gitee download_url 拉 .bin.zip
      2. 解压并校验结构（必须包含 .bin/src/main.py）
      3. 写入「待应用更新」标记：项目根/.pending_update + .bin_update/
      4. 清理历史残留临时文件：.pending_update / .bin_update / .bin_backup
      5. 提供 trigger_restart 的参数构造 helper（HTTP 路由层直接用）
    不做的事（避免耦合）：
      - 不读/解析远程 version.json（归 VersionService）
      - 不真正 fork 子进程、不重启父进程（归 HTTP 路由层，因为需要先发响应）
      - 不备份/替换运行中的 .bin/（归 restarter.py）
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def download_update(self, download_url: str, target_version: str, *, force: bool = True) -> Dict[str, Any]:
        """下载指定版本更新包并准备到 .bin_update + .pending_update

        Args:
            download_url: 远程 zip 地址（来自 version.json.versions[i].download_url）
            target_version: 目标版本号，仅用于日志和写标记
            force: 强制重新下载——True 时始终先清旧残留再下载，保证每次点击都拿到 Gitee 最新
        """
        project_root = BASE_DIR.parent
        update_dir = project_root / '.bin_update'
        pending_marker = project_root / '.pending_update'
        backup_dir = project_root / '.bin_backup'
        local_version_file = project_root / VERSION_JSON_PATH
        tmp_dir = None

        # --- 1. 强制清理旧残留：放在 URL 校验之前执行！
        # 任何一次进入 download_update，不管最后 URL 是否合法，都先清掉陈旧的
        # .pending_update / .bin_update / .bin_backup，确保不会把旧包误判为新的。
        # 这也是需求1的核心：每次点「更新到此版本」一定是从 Gitee 重新下载。
        if pending_marker.exists():
            try:
                pending_marker.unlink()
            except Exception:
                pass
        if update_dir.exists():
            shutil.rmtree(update_dir, ignore_errors=True)
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        # --- 2. 输入校验 ---------------------------------------------------
        if not download_url or not download_url.startswith(('http://', 'https://')):
            return {'success': False, 'message': '下载地址无效，请检查 version.json 中的 download_url 字段', 'restart_required': False}

        try:
            # --- 3. 下载 zip 到临时目录 -----------------------------------
            tmp_dir = Path(tempfile.mkdtemp(prefix='album_update_'))
            zip_path = tmp_dir / 'update.zip'

            req = urllib.request.Request(
                download_url,
                headers={
                    'User-Agent': 'AlbumViewerUpdater',
                    'Accept': 'application/zip, application/octet-stream, */*',
                },
            )
            with urllib.request.urlopen(req, timeout=300) as resp, open(zip_path, 'wb') as f:
                shutil.copyfileobj(resp, f, length=64 * 1024)

            if not zipfile.is_zipfile(zip_path):
                return {'success': False, 'message': '下载的文件不是合法的 zip 压缩包', 'restart_required': False}

            # --- 4. 解压 + 路径穿越校验 -----------------------------------
            extract_dir = tmp_dir / 'extracted'
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for info in zf.infolist():
                    target = (extract_dir / info.filename).resolve()
                    try:
                        target.relative_to(extract_dir.resolve())
                    except ValueError:
                        return {'success': False, 'message': '更新包包含非法路径（路径穿越）', 'restart_required': False}
                zf.extractall(extract_dir)

            # --- 5. 找到新的 .bin/ 目录（通过 .bin/src/main.py 锚点）-----
            new_bin_dir = self._locate_new_bin_dir(extract_dir)
            if new_bin_dir is None:
                return {
                    'success': False,
                    'message': '更新包内找不到合法的程序目录（.bin/src/main.py），请确认下载地址是否正确',
                    'restart_required': False,
                }

            # --- 6. 拷贝到项目根/.bin_update/ ----------------------------
            shutil.copytree(new_bin_dir, update_dir, symlinks=False)

            # --- 7. 更新本地 version.json 的 latest_version（仅做记录）--
            if target_version:
                self._record_local_version(local_version_file, target_version, download_url)

            # --- 8. 写 .pending_update 标记，restarter.py 下次启动据此应用
            marker_data = {
                'version': str(target_version or '').strip(),
                'prepared_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'backup_dir': str(backup_dir),
            }
            pending_marker.write_text(
                json.dumps(marker_data, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )

            return {
                'success': True,
                'message': '更新包已准备完成，正在自动重启应用更新...',
                'restart_required': True,
                'backup_dir': str(backup_dir),
                'force_download': True,
            }
        except Exception as e:
            # 失败兜底：任何异常都把半拉子的 .bin_update 删掉，避免下次误判
            if update_dir.exists():
                shutil.rmtree(update_dir, ignore_errors=True)
            if pending_marker.exists():
                try:
                    pending_marker.unlink()
                except Exception:
                    pass
            return {'success': False, 'message': f'准备更新失败: {str(e)}', 'restart_required': False}
        finally:
            if tmp_dir and tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def cleanup_tempfiles() -> None:
        """清理所有更新相关临时文件：.pending_update / .bin_update / .bin_backup

        这是一个对外暴露的纯静态 helper，restarter.py 已实现自己的版本，这里放一份给 HTTP/管理工具兜底调用。
        """
        project_root = BASE_DIR.parent
        pending_marker = project_root / '.pending_update'
        update_dir = project_root / '.bin_update'
        backup_dir = project_root / '.bin_backup'
        for label, path, kind in [
            ('.pending_update', pending_marker, 'file'),
            ('.bin_update', update_dir, 'dir'),
            ('.bin_backup', backup_dir, 'dir'),
        ]:
            if not path.exists():
                continue
            try:
                if kind == 'file':
                    path.unlink()
                else:
                    shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # trigger-restart 参数构造 helper（给 VersionRouter 用，避免耦合 main_router 代码）
    # ------------------------------------------------------------------
    @staticmethod
    def build_trigger_restart_cmd(project_root: Path, python_bin: str, port: int, delay_ms: int = 1200) -> list:
        """返回用于 Popen 的 cmd 列表：调用 restarter.py（带 delay + kill parent）

        Args:
            project_root: 项目根目录（Path 对象）
            python_bin: 解释器路径，通常是 sys.executable
            port: 当前 HTTP 服务监听端口，restarter 会用它等端口就绪
            delay_ms: kill 父进程前等待的毫秒数，默认 1200ms，保证 HTTP 响应发送完毕
        """
        restarter_py = project_root / '.bin' / 'src' / 'restarter.py'
        return [
            python_bin,
            str(restarter_py),
            '--delay-before-kill', f'{max(0, int(delay_ms))}',
            '--port', str(int(port)),
            '--kill-parent', str(os.getpid()),
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _locate_new_bin_dir(extract_dir: Path):
        """通过「rglob main.py + 父目录是 src + 祖父目录是 .bin」锚点找到解压后的新 .bin/"""
        for candidate in extract_dir.rglob('main.py'):
            parts = candidate.parts
            try:
                src_idx = parts.index('src')
            except ValueError:
                continue
            if src_idx > 0 and parts[src_idx - 1] == '.bin':
                return candidate.parent.parent  # => .bin/
        return None

    @staticmethod
    def _record_local_version(local_version_file: Path, target_version: str, download_url: str) -> None:
        """把目标版本写进本地 version.json（失败不抛，仅静默跳过；只做记录不影响主流程）"""
        target_version = str(target_version or '').strip()
        if not target_version:
            return
        try:
            if local_version_file.exists():
                data = json.loads(local_version_file.read_text(encoding='utf-8'))
            else:
                data = {'latest_version': '', 'versions': []}
            data['latest_version'] = target_version
            existing = any(str(v.get('version', '')).strip() == target_version for v in data.get('versions', []))
            if not existing:
                vers = list(data.get('versions', []))
                vers.insert(0, {
                    'version': target_version,
                    'date': time.strftime('%Y-%m-%d'),
                    'changelog': '',
                    'download_url': download_url,
                })
                data['versions'] = vers
            local_version_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
        except Exception:
            pass
