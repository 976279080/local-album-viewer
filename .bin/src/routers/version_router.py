#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本检查路由 Mixin"""

from services.version_service import VersionService


class VersionRouterMixin:
    """版本检查 API 路由：check, list, download"""

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
        """POST /api/version/restart - 触发自动重启并应用更新（无需密码认证）"""
        try:
            ok, msg = VersionService.trigger_restart_and_apply_update()
            if ok:
                self.send_json({'status': 'ok', 'message': msg})
            else:
                self.send_json({'status': 'error', 'message': msg}, status=400)
        except Exception as e:
            self.send_error_json(f'重启失败: {str(e)}')
