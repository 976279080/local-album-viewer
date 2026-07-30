#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本检查路由 Mixin"""

import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path

from services.version_service import VersionService


class VersionRouterMixin:
    """版本检查 API 路由：check, list, download, restart"""

    def handle_version_list(self, query) -> None:
        """GET /api/version/list - 获取完整版本列表（无需认证）"""
        try:
            svc = VersionService()
            result = svc.get_version_list()
            self.send_json({'status': 'ok', **result})
        except Exception as e:
            self.send_error_json(f'获取版本列表失败: {str(e)}')

    def handle_version_check(self, query) -> None:
        """GET /api/version/check - 检查版本更新（无需认证）"""
        try:
            svc = VersionService()
            result = svc.check_version()
            self.send_json({'status': 'ok', **result})
        except Exception as e:
            self.send_error_json(f'版本检查失败: {str(e)}')

    def handle_version_download(self) -> None:
        """POST /api/version/download - 下载并准备更新包（需密码认证）

        请求体：{ "download_url": str, "version": str }
        下载与解压可能耗时较长（几秒到几十秒），由前端展示 loading 状态。
        """
        try:
            if not self.check_auth():
                return
            try:
                body = self.parse_request_body()
            except ValueError:
                self.send_error_json('请求体格式错误')
                return
            download_url = str(body.get('download_url', '') or '').strip()
            target_version = str(body.get('version', '') or '').strip()
            if not download_url:
                self.send_error_json('缺少 download_url 参数')
                return

            svc = VersionService()
            result = svc.download_update(download_url, target_version)
            if result.get('success'):
                self.send_json({'status': 'ok', **result})
            else:
                self.send_json({'status': 'error', **result}, status=400)
        except Exception as e:
            self.send_error_json(f'准备更新失败: {str(e)}')

    def handle_version_restart(self) -> None:
        """POST /api/version/restart - 触发自动重启（无需认证）

        将 restart.py 复制到临时目录并以 detached 进程启动，
        然后返回成功响应。前端收到响应后显示重启中遮罩。
        restart.py 负责：杀旧进程 → 应用更新 → 启动服务 → 打开浏览器。
        """
        try:
            # 定位 restart.py
            restart_src = Path(__file__).resolve().parent.parent / 'restart.py'
            if not restart_src.exists():
                self.send_error_json('重启脚本不存在')
                return

            # 复制到临时目录（避免 .bin 被替换时文件锁定）
            tmp_script = Path(tempfile.gettempdir()) / 'album_restart.py'
            shutil.copy2(str(restart_src), str(tmp_script))

            # 通过环境变量传递项目根路径
            project_root = Path(__file__).resolve().parent.parent.parent
            env = os.environ.copy()
            env['ALBUM_PROJECT_ROOT'] = str(project_root)

            # 以 detached 进程启动
            creationflags = 0
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW

            subprocess.Popen(
                [sys.executable, str(tmp_script)],
                env=env,
                startupinfo=startupinfo,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            self.send_json({'status': 'ok', 'message': '重启已触发'})
        except Exception as e:
            self.send_error_json(f'触发重启失败: {str(e)}')
