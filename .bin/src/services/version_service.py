#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本检查服务模块 - 封装版本检查业务逻辑
遵循单一职责原则：仅负责「从本地+远程 version.json 读取版本信息」，
下载/解压/写标记等更新包准备工作已解耦到 UpdateService（update_service.py）。
"""

import json
import urllib.request
import urllib.error
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
        """下载并准备更新包（具体工作已解耦到 UpdateService）

        VersionService 仅做转发：每次调用都强制从 download_url 重新下载，保证用户每次点
        「更新到此版本」一定拿到 Gitee 上最新的包，不复用旧 .bin_update 缓存。
        """
        try:
            from .update_service import UpdateService
        except Exception:
            from services.update_service import UpdateService
        return UpdateService().download_update(
            download_url,
            target_version,
            force=True,
        )

    @staticmethod
    def _now_str() -> str:
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
