#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""授权管理路由 Mixin"""

from db import get_config, set_config
from services.license_service import LicenseService

# 允许通过 API 读取/修改的授权配置项白名单
_LICENSE_CONFIG_KEYS = {
    'license_secret_key': {'label': '授权码签名密钥', 'type': 'str'},
    'free_trial_days': {'label': '免费试用期（天）', 'type': 'int'},
    'license_monthly_days': {'label': '月卡有效期（天）', 'type': 'int'},
    'license_yearly_days': {'label': '年卡有效期（天）', 'type': 'int'},
}


class LicenseRouterMixin:
    """授权管理 API 路由：status / activate / clear / config"""

    @property
    def license_service(self):
        """懒加载授权服务（避免在 __init__ 阶段与 BaseHTTPRequestHandler 的初始化顺序冲突）"""
        if not hasattr(self, '_license_service') or self._license_service is None:
            self._license_service = LicenseService()
        return self._license_service

    def handle_license_status(self, query) -> None:
        """获取授权状态（无需认证）"""
        try:
            status = self.license_service.get_license_status()
            self.send_json({'status': 'ok', **status})
        except Exception as e:
            self.send_error_json(f'获取授权状态失败: {str(e)}')

    def handle_license_activate(self) -> None:
        """激活授权码（无需认证）"""
        try:
            data = self.parse_request_body()
            code = str(data.get('code', '')).strip()
        except Exception:
            self.send_error_json('Invalid request body')
            return

        try:
            result = self.license_service.activate_license(code)
            self.send_json(result)
        except Exception as e:
            self.send_error_json(f'激活失败: {str(e)}')

    def handle_license_clear(self) -> None:
        """清除授权码（需认证）"""
        if not self.check_auth():
            return

        try:
            self.license_service.clear_license()
            self.send_json({'status': 'ok', 'message': '授权码已清除'})
        except Exception as e:
            self.send_error_json(f'清除授权码失败: {str(e)}')

    def handle_verify(self) -> None:
        """验证密码（无副作用，仅校验 X-Auth 头）"""
        if not self.check_auth():
            return
        self.send_json({'status': 'ok'})

    def handle_get_license_config(self, query) -> None:
        """获取授权配置项（GET，必须带内部工具标识Header）"""
        if not self._verify_internal_tool():
            self.send_error_json('禁止直接访问', 403)
            return

        try:
            items = []
            for key, meta in _LICENSE_CONFIG_KEYS.items():
                value = get_config(key)
                items.append({
                    'key': key,
                    'label': meta['label'],
                    'type': meta['type'],
                    'value': value,
                })
            self.send_json({'status': 'ok', 'items': items})
        except Exception as e:
            self.send_error_json(f'获取配置失败: {str(e)}')

    def handle_set_license_config(self) -> None:
        """修改授权配置项（POST，需密码认证 + 内部工具Header）"""
        if not self._verify_internal_tool():
            self.send_error_json('禁止直接访问', 403)
            return

        if not self.check_auth():
            return

        try:
            data = self.parse_request_body()
            key = str(data.get('key', '')).strip()
            value = str(data.get('value', '')).strip()
        except Exception:
            self.send_error_json('Invalid request body')
            return

        if key not in _LICENSE_CONFIG_KEYS:
            self.send_error_json(f'未知配置项: {key}')
            return

        meta = _LICENSE_CONFIG_KEYS[key]
        if meta['type'] == 'int':
            try:
                int(value)
            except ValueError:
                self.send_error_json(f'{meta["label"]}必须是整数')
                return

        try:
            old_value = get_config(key)
            set_config(key, value)
            self.send_json({
                'status': 'ok',
                'message': f'{meta["label"]}已更新',
                'key': key,
                'old_value': old_value,
                'new_value': value,
            })
        except Exception as e:
            self.send_error_json(f'更新配置失败: {str(e)}')

    def _verify_internal_tool(self) -> bool:
        """校验请求是否来自内部工具页面（防止直接访问API）"""
        return self.headers.get('X-Internal-Tool') == 'qorder-license-tool'
