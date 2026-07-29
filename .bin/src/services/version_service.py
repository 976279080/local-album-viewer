#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本检查服务模块 - 封装版本检查业务逻辑
遵循单一职责原则：仅负责版本检查与比较
"""

import json
import urllib.request
import urllib.error

from config import APP_VERSION, GITEE_RAW_BASE, VERSION_JSON_PATH, VERSION_CHECK_TIMEOUT, BASE_DIR


class VersionService:
    """版本检查服务类"""

    def get_version_list(self) -> dict:
        """
        获取完整版本列表

        Returns:
            {
                'local_version': str,
                'latest_version': str or None,
                'versions': list,   # [{version, date, changelog, download_url}, ...]
                'error': str
            }
        """
        result = {
            'local_version': APP_VERSION,
            'latest_version': None,
            'versions': [],
            'error': '',
        }

        url = f"{GITEE_RAW_BASE}/{VERSION_JSON_PATH}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'QorderVersionChecker'})
            with urllib.request.urlopen(req, timeout=VERSION_CHECK_TIMEOUT) as resp:
                raw = resp.read().decode('utf-8')
            data = json.loads(raw)
        except Exception as e:
            # 远程获取失败，尝试读取本地 version.json 作为回退
            local_version_file = BASE_DIR.parent / VERSION_JSON_PATH
            try:
                raw = local_version_file.read_text(encoding='utf-8')
                data = json.loads(raw)
            except Exception:
                result['error'] = f'获取版本信息失败: {str(e)}'
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
                    'download_url': '',
                }]
                latest = ver

        result['versions'] = versions
        result['latest_version'] = latest or None
        return result

    def check_version(self) -> dict:
        """
        检查版本更新

        Returns:
            {
                'local_version': str,
                'remote_version': str or None,
                'has_update': bool,
                'changelog': str,
                'release_date': str,
                'error': str  # 失败时有值
            }
        """
        result = {
            'local_version': APP_VERSION,
            'remote_version': None,
            'has_update': False,
            'changelog': '',
            'release_date': '',
            'error': '',
        }

        url = f"{GITEE_RAW_BASE}/{VERSION_JSON_PATH}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'QorderVersionChecker'})
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

        remote_version = str(data.get('version', '')).strip()
        if not remote_version:
            result['error'] = '远程版本信息无效'
            return result

        changelog = str(data.get('changelog', '') or '')
        release_date = str(data.get('release_date', '') or '')

        result['remote_version'] = remote_version
        result['changelog'] = changelog
        result['release_date'] = release_date

        try:
            cmp = self._compare_versions(APP_VERSION, remote_version)
            result['has_update'] = cmp < 0
        except Exception as e:
            result['error'] = f'版本比较失败: {str(e)}'

        return result

    def _compare_versions(self, v1: str, v2: str) -> int:
        """
        比较两个版本号

        Returns:
            -1: v1 < v2
             0: v1 == v2
             1: v1 > v2
        """
        parts1 = [int(p) for p in v1.split('.')]
        parts2 = [int(p) for p in v2.split('.')]

        # 对齐长度，不足的补 0
        max_len = max(len(parts1), len(parts2))
        parts1 += [0] * (max_len - len(parts1))
        parts2 += [0] * (max_len - len(parts2))

        for a, b in zip(parts1, parts2):
            if a < b:
                return -1
            if a > b:
                return 1
        return 0
