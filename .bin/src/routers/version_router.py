#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本检查路由 Mixin"""

from services.version_service import VersionService


class VersionRouterMixin:
    """版本检查 API 路由：check, list"""

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
