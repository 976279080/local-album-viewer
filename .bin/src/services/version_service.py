#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本检查服务模块 - 封装版本检查业务逻辑
遵循单一职责原则：仅负责版本检查与比较

更新逻辑：
  - 本地版本号来源：项目根目录 version.json -> latest_version
  - 远程版本号来源：GITEE_RAW_BASE + version.json -> latest_version
  - 若远程版本号 > 本地版本号，则存在更新
  - 下载地址来源：version.json 中每个版本的 download_url 字段（完整 URL）
  - 下载的 zip 仅包含 .bin/ 目录，解压后替换本地 .bin
"""

import json
import os
import shutil
import tempfile
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

from config import GITEE_RAW_BASE, VERSION_JSON_PATH, VERSION_CHECK_TIMEOUT, BASE_DIR


def _read_local_version_json() -> dict:
    """读取本地 version.json，失败返回空 dict"""
    try:
        p = BASE_DIR.parent / VERSION_JSON_PATH
        data = json.loads(p.read_text(encoding='utf-8'))
        return data
    except Exception:
        return {}


class VersionService:
    """版本检查服务类"""

    def get_version_list(self) -> dict:
        """
        获取完整版本列表

        Returns:
            {
                'local_version': str,
                'latest_version': str or None,
                'versions': list,
                'error': str
            }
        """
        local_data = _read_local_version_json()
        local_version = str(local_data.get('latest_version', '') or '').strip()

        result = {
            'local_version': local_version,
            'latest_version': None,
            'versions': [],
            'error': '',
        }

        url = f"{GITEE_RAW_BASE}/{VERSION_JSON_PATH}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'AlbumViewerVersionChecker'})
            with urllib.request.urlopen(req, timeout=VERSION_CHECK_TIMEOUT) as resp:
                raw = resp.read().decode('utf-8')
            data = json.loads(raw)
        except Exception as e:
            result['error'] = f'获取版本信息失败: {str(e)}'
            if local_data:
                vers = local_data.get('versions', [])
                lv = str(local_data.get('latest_version', '') or '').strip()
                result['latest_version'] = lv or None
                for v in vers:
                    v.setdefault('date', '')
                    v.setdefault('changelog', '')
                    v.setdefault('download_url', '')
                result['versions'] = vers
            return result

        versions = data.get('versions', [])
        latest = str(data.get('latest_version', '') or '').strip()

        # 兼容旧格式（单版本对象）
        if not versions:
            ver = str(data.get('version', '')).strip()
            if ver:
                versions = [{
                    'version': ver,
                    'date': str(data.get('release_date', '') or ''),
                    'changelog': str(data.get('changelog', '') or ''),
                    'download_url': str(data.get('download_url', '') or ''),
                }]
                latest = ver

        # 补齐缺失字段（download_url 由 version.json 提供，不自动构造）
        for v in versions:
            v.setdefault('date', '')
            v.setdefault('changelog', '')
            v.setdefault('download_url', '')

        result['versions'] = versions
        result['latest_version'] = latest or None
        return result

    def check_version(self) -> dict:
        """
        检查版本更新

        比较：远程 version.json.latest_version vs 本地 version.json.latest_version
        """
        local_data = _read_local_version_json()
        local_version = str(local_data.get('latest_version', '') or '').strip()

        result = {
            'local_version': local_version,
            'remote_version': None,
            'has_update': False,
            'changelog': '',
            'release_date': '',
            'download_url': '',
            'error': '',
        }

        url = f"{GITEE_RAW_BASE}/{VERSION_JSON_PATH}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'AlbumViewerVersionChecker'})
            with urllib.request.urlopen(req, timeout=VERSION_CHECK_TIMEOUT) as resp:
                raw = resp.read().decode('utf-8')
            data = json.loads(raw)
        except urllib.error.HTTPError as e:
            result['error'] = f'网络请求失败: HTTP {e.code}'
            return result
        except urllib.error.URLError as e:
            result['error'] = f'网络请求失败: {str(e.reason if hasattr(e, "reason") else e)}'
            return result
        except Exception as e:
            result['error'] = f'网络请求失败: {str(e)}'
            return result

        remote_version = str(data.get('latest_version', '') or data.get('version', '')).strip()
        if not remote_version:
            result['error'] = '远程版本信息无效'
            return result

        # 读取最新版本的 changelog 等信息
        versions = data.get('versions', []) or []
        latest_info = {}
        for v in versions:
            if str(v.get('version', '')).strip() == remote_version:
                latest_info = v
                break
        if not latest_info and versions:
            latest_info = versions[0]

        changelog = str(latest_info.get('changelog', '') or '')
        release_date = str(latest_info.get('date', '') or latest_info.get('release_date', '') or '')
        download_url = str(latest_info.get('download_url', '') or '')

        result['remote_version'] = remote_version
        result['changelog'] = changelog
        result['release_date'] = release_date
        result['download_url'] = download_url

        try:
            cmp = self._compare_versions(local_version, remote_version)
            result['has_update'] = cmp < 0
        except Exception as e:
            result['error'] = f'版本比较失败: {str(e)}'

        return result

    def _compare_versions(self, v1: str, v2: str) -> int:
        parts1 = [int(p) for p in v1.split('.')]
        parts2 = [int(p) for p in v2.split('.')]
        max_len = max(len(parts1), len(parts2))
        parts1 += [0] * (max_len - len(parts1))
        parts2 += [0] * (max_len - len(parts2))
        for a, b in zip(parts1, parts2):
            if a < b:
                return -1
            if a > b:
                return 1
        return 0

    def download_update(self, download_url: str, target_version: str = '') -> dict:
        """
        下载更新包并准备下次启动时替换

        流程：
          1. 下载 zip → 临时目录（URL 为空则按规则基于 target_version 构造）
          2. 解压 → 查找里面的 .bin/ 目录
          3. 将 .bin/ 复制到项目根的 .bin_update/
          4. 写入 .pending_update 标记，更新本地 version.json
          5. 清理临时文件
        """
        project_root = BASE_DIR.parent
        update_dir = project_root / '.bin_update'
        pending_marker = project_root / '.pending_update'
        backup_dir = project_root / '.bin_backup'
        local_version_file = project_root / VERSION_JSON_PATH
        tmp_dir = None

        # download_url 必须由 version.json 提供，不再自动构造
        if not download_url or not download_url.startswith(('http://', 'https://')):
            return {'success': False, 'message': '下载地址无效，请检查 version.json 中的 download_url 字段', 'restart_required': False}

        if pending_marker.exists() and update_dir.is_dir():
            return {
                'success': False,
                'message': '已有待应用的更新包，请先重启程序以完成更新',
                'restart_required': True,
            }

        try:
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

            found_bin_src = None
            for candidate in extract_dir.rglob('main.py'):
                parts = candidate.parts
                try:
                    src_idx = parts.index('src')
                    if src_idx > 0 and parts[src_idx - 1] == '.bin':
                        found_bin_src = candidate
                        break
                except ValueError:
                    continue

            if found_bin_src is None:
                return {
                    'success': False,
                    'message': '更新包内找不到合法的程序目录（.bin/src/main.py），请确认下载地址是否正确',
                    'restart_required': False,
                }
            new_bin_dir = found_bin_src.parent.parent

            if update_dir.exists():
                shutil.rmtree(update_dir, ignore_errors=True)
            shutil.copytree(new_bin_dir, update_dir, symlinks=False)

            # 更新本地 version.json latest_version
            if target_version:
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
                            'date': self._now_str()[:10],
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

            marker_info = {
                'version': target_version,
                'prepared_at': self._now_str(),
                'backup_dir': str(backup_dir),
            }
            pending_marker.write_text(
                json.dumps(marker_info, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )

            return {
                'success': True,
                'message': '更新包已准备完成，请关闭浏览器并重新双击启动脚本以应用更新',
                'restart_required': True,
                'backup_dir': str(backup_dir),
            }

        except urllib.error.HTTPError as e:
            return {
                'success': False,
                'message': f'下载失败：HTTP {e.code}',
                'restart_required': False,
            }
        except urllib.error.URLError as e:
            reason = str(e.reason if hasattr(e, "reason") else e)
            return {
                'success': False,
                'message': f'下载失败：网络错误（{reason}）',
                'restart_required': False,
            }
        except zipfile.BadZipFile:
            return {'success': False, 'message': '更新包损坏，不是合法 zip 文件', 'restart_required': False}
        except (OSError, shutil.Error) as e:
            return {
                'success': False,
                'message': f'准备更新失败，磁盘操作错误：{str(e)}',
                'restart_required': False,
            }
        finally:
            if tmp_dir and tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def _now_str() -> str:
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
