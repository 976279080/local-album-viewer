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
import ssl
from pathlib import Path

from config import GITEE_RAW_BASE, GITHUB_RAW_BASE, VERSION_JSON_PATH, VERSION_CHECK_TIMEOUT, BASE_DIR


def _fetch_version_json() -> dict:
    """从远程获取 version.json，Gitee 失败时自动回退 GitHub"""
    urls = [f"{GITEE_RAW_BASE}/{VERSION_JSON_PATH}"]
    if GITHUB_RAW_BASE:
        urls.append(f"{GITHUB_RAW_BASE}/{VERSION_JSON_PATH}")

    last_error = None
    for url in urls:
        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(url, headers={'User-Agent': 'AlbumViewerVersionChecker'})
            with urllib.request.urlopen(req, timeout=VERSION_CHECK_TIMEOUT, context=ctx) as resp:
                raw = resp.read().decode('utf-8')
            return json.loads(raw)
        except Exception as e:
            last_error = e
            continue

    # 全部失败
    raise last_error


def _is_version_stable(v: dict) -> bool:
    """判断一个版本是否为「稳定版」

    判定规则（按优先级）：
      1. 有显式 `stable` 字段（bool 或 "stable"/"true" 字符串）→ 按字段值
      2. 有 `channel` / `tag` 字段（字符串）→ 非 "beta"/"alpha"/"dev"/"rc"/"canary"/"nightly"/"test" 视为稳定
      3. 版本号字符串里含上述非稳定关键字 → 非稳定
      4. 默认：稳定
    """
    # 1) 显式 stable 字段
    if 'stable' in v and v['stable'] is not None:
        s = v['stable']
        if isinstance(s, bool):
            return s
        if isinstance(s, (int, float)):
            return bool(s)
        sv = str(s).strip().lower()
        if sv in ('true', '1', 'stable', 'yes', 'y'):
            return True
        if sv in ('false', '0', 'no', 'n', 'beta', 'alpha', 'dev', 'rc', 'canary', 'nightly', 'test'):
            return False

    UNSTABLE_KEYS = ('beta', 'alpha', 'dev', 'rc', 'canary', 'nightly', 'test', 'pre', 'preview')

    # 2) channel / tag 字段
    for key in ('channel', 'tag'):
        if key in v:
            cv = str(v[key] or '').strip().lower()
            if cv:
                for k in UNSTABLE_KEYS:
                    if k in cv:
                        return False

    # 3) 版本号本身含非稳定字
    ver_s = str(v.get('version') or '').strip().lower()
    for k in UNSTABLE_KEYS:
        if k in ver_s:
            return False
    return True


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

    @staticmethod
    def _pick_latest_version(versions, stable_only: bool):
        """按版本号排序取最高。stable_only=True 时只在稳定版里挑"""
        if not versions:
            return None
        def parse_ver(v):
            s = str(v.get('version') or '0').strip().lower()
            # 去掉非稳定后缀再比（保证 0.0.3-beta < 0.0.3）
            for suf in ('-beta', '-alpha', '-dev', '-rc', '-canary', '-nightly', '-test', '-pre', '-preview'):
                if suf in s:
                    s = s.split(suf)[0]
            parts = []
            for p in s.replace('v', '').split('.'):
                try:
                    parts.append(int(''.join(c for c in p if c.isdigit()) or 0))
                except Exception:
                    parts.append(0)
            return tuple(parts + [0, 0, 0])
        pool = [v for v in versions if _is_version_stable(v)] if stable_only else list(versions)
        if not pool:
            return None
        return max(pool, key=parse_ver)

    def get_version_list(self) -> dict:
        """
        获取完整版本列表

        Returns:
            {
                'local_version': str,
                'latest_version': str or None,         # 所有通道最新
                'latest_stable_version': str or None,  # 稳定通道最新（前端小红点 + 更新权限用这个比）
                'versions': [ { ..., is_stable: bool } ],
                'error': str
            }
        """
        local_data = _read_local_version_json()
        local_version = str(local_data.get('latest_version', '') or '').strip()

        result = {
            'local_version': local_version,
            'latest_version': None,
            'latest_stable_version': None,
            'versions': [],
            'error': '',
        }

        try:
            data = _fetch_version_json()
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
                    v['is_stable'] = _is_version_stable(v)
                result['versions'] = vers
                lst = self._pick_latest_version(vers, stable_only=True)
                if lst:
                    result['latest_stable_version'] = str(lst.get('version') or '') or None
                else:
                    result['latest_stable_version'] = lv or None
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

        # 补齐缺失字段 + 注入 is_stable
        for v in versions:
            v.setdefault('date', '')
            v.setdefault('changelog', '')
            v.setdefault('download_url', '')
            v['is_stable'] = _is_version_stable(v)

        result['versions'] = versions

        # 全通道最新
        if latest:
            result['latest_version'] = latest
        else:
            lv = self._pick_latest_version(versions, stable_only=False)
            if lv:
                result['latest_version'] = str(lv.get('version') or '') or None

        # 稳定通道最新（这个才是前端小红点/更新按钮权限要用的）
        ls = self._pick_latest_version(versions, stable_only=True)
        if ls:
            result['latest_stable_version'] = str(ls.get('version') or '') or None
        else:
            # 如果远程真的没有稳定版，兜底用 latest_version
            result['latest_stable_version'] = result['latest_version']
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

        try:
            data = _fetch_version_json()
        except Exception as e:
            result['error'] = f'获取版本信息失败: {str(e)}'
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
