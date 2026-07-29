#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
授权服务模块 - 封装授权状态管理业务逻辑
遵循单一职责原则：仅负责授权码激活、状态查询与首次上传记录
"""

import time
from typing import Any, Dict

from db import (
    get_config,
    set_config,
    delete_config,
)
from utils.license_config import get_free_trial_days
from utils.license_util import verify_license

# 配置键名
KEY_FIRST_UPLOAD_TIME = 'first_upload_time'
KEY_LICENSE_CODE = 'license_code'
KEY_LICENSE_CODE_TYPE = 'license_code_type'
KEY_LICENSE_EXPIRE_TIME = 'license_expire_time'


class LicenseService:
    """授权服务类"""

    def get_license_status(self) -> Dict[str, Any]:
        """获取授权状态

        Returns:
            {
                'first_upload_time': int/None,
                'has_license': bool,
                'license_type': str,
                'license_expire_time': int/None,
                'remaining_days': int,
                'in_free_trial': bool,
                'free_trial_remaining_days': int,
            }
        """
        first_upload_time_str = get_config(KEY_FIRST_UPLOAD_TIME)
        license_code = get_config(KEY_LICENSE_CODE)

        first_upload_time = int(first_upload_time_str) if first_upload_time_str else None

        # 免费试用期计算
        in_free_trial = False
        free_trial_remaining_days = 0
        if first_upload_time is not None:
            now = int(time.time())
            trial_end = first_upload_time + get_free_trial_days() * 86400
            if now < trial_end:
                in_free_trial = True
                free_trial_remaining_days = max(0, (trial_end - now + 86399) // 86400)

        # 授权码校验（直接使用 DB 存储的过期时间，支持叠加后的修正值）
        has_license = False
        license_type = ''
        license_expire_time = None
        remaining_days = 0

        if license_code:
            stored_type = get_config(KEY_LICENSE_CODE_TYPE)
            stored_expire_str = get_config(KEY_LICENSE_EXPIRE_TIME)

            if stored_expire_str == '':
                # 永久卡
                has_license = True
                license_type = 'permanent'
                license_expire_time = None
                remaining_days = -1
            elif stored_expire_str is not None:
                try:
                    stored_expire = int(stored_expire_str)
                    now = int(time.time())
                    if now <= stored_expire:
                        has_license = True
                        license_type = stored_type or ''
                        license_expire_time = stored_expire
                        remaining_days = max(0, (stored_expire - now + 86399) // 86400)
                except (ValueError, TypeError):
                    # 存储值异常，回退到解析授权码
                    pass

            # 兜底：DB 存储读取失败时，重新解析授权码内嵌时间
            if not has_license:
                result = verify_license(license_code)
                if result.get('valid'):
                    has_license = True
                    license_type = result.get('code_type', '')
                    license_expire_time = result.get('expire_time')
                    remaining_days = result.get('remaining_days', 0)

        return {
            'first_upload_time': first_upload_time,
            'has_license': has_license,
            'license_type': license_type,
            'license_expire_time': license_expire_time,
            'remaining_days': remaining_days,
            'in_free_trial': in_free_trial,
            'free_trial_remaining_days': free_trial_remaining_days,
        }

    def activate_license(self, code: str) -> Dict[str, Any]:
        """激活授权码（支持在已有授权基础上叠加天数）

        Args:
            code: 授权码字符串

        Returns:
            {
                'success': bool,
                'message': str,
                'license_type': str,
                'expire_time': int/None,
                'stacked': bool,          # 是否为叠加激活
                'added_days': int,        # 本次新增天数（临时卡）
                'total_days': int,        # 叠加后总天数（临时卡，永久卡为-1）
            }
        """
        now = int(time.time())

        if not code or not isinstance(code, str):
            return {
                'success': False,
                'message': '授权码不能为空',
                'license_type': '',
                'expire_time': None,
                'stacked': False,
                'added_days': 0,
                'total_days': 0,
            }

        # 1. 校验新授权码签名
        result = verify_license(code)
        if not result.get('valid'):
            return {
                'success': False,
                'message': result.get('error', '授权码无效'),
                'license_type': '',
                'expire_time': None,
                'stacked': False,
                'added_days': 0,
                'total_days': 0,
            }

        new_code_type = result.get('code_type', '')
        new_expire_time = result.get('expire_time')

        # 2. 读取当前授权状态（直接读 DB，不重新走 verify_license 兜底）
        existing_code = get_config(KEY_LICENSE_CODE)
        existing_type_str = get_config(KEY_LICENSE_CODE_TYPE)
        existing_expire_str = get_config(KEY_LICENSE_EXPIRE_TIME)

        existing_is_permanent = (
            existing_code and existing_expire_str == ''
        )
        existing_remaining_days = 0
        if (
            existing_code
            and not existing_is_permanent
            and existing_expire_str
        ):
            try:
                existing_expire = int(existing_expire_str)
                if existing_expire > now:
                    existing_remaining_days = max(
                        0, (existing_expire - now + 86399) // 86400
                    )
            except (ValueError, TypeError):
                existing_remaining_days = 0

        stacked = bool(existing_code) and not existing_is_permanent

        # 3. 永久卡规则：任一方为永久卡则结果为永久卡
        if new_code_type == 'permanent' or existing_is_permanent:
            final_type = 'permanent'
            final_expire_time = None
            final_expire_str = ''
            added_days = 0
            total_days = -1
            if existing_is_permanent and new_code_type != 'permanent':
                message = '当前已是永久授权，无需额外激活'
                stacked = False
            elif existing_is_permanent and new_code_type == 'permanent':
                message = '当前已是永久授权'
                stacked = False
            else:
                message = '永久授权激活成功，感谢您的支持'
        else:
            # 4. 临时卡：计算叠加天数
            new_remaining_days = max(
                0, (new_expire_time - now + 86399) // 86400
            )
            added_days = new_remaining_days
            total_days = existing_remaining_days + new_remaining_days
            final_expire_time = now + total_days * 86400
            final_expire_str = str(final_expire_time)
            final_type = (
                existing_type_str
                if existing_type_str in ('monthly', 'yearly')
                else new_code_type
            )
            if stacked:
                message = (
                    f'授权成功，已在现有授权基础上叠加 {new_remaining_days} 天，'
                    f'共 {total_days} 天'
                )
            else:
                message = f'授权成功，有效期 {total_days} 天'

        # 5. 存储最终状态
        set_config(KEY_LICENSE_CODE, code)
        set_config(KEY_LICENSE_CODE_TYPE, final_type)
        set_config(KEY_LICENSE_EXPIRE_TIME, final_expire_str)

        return {
            'success': True,
            'message': message,
            'license_type': final_type,
            'expire_time': final_expire_time,
            'stacked': stacked,
            'added_days': added_days,
            'total_days': total_days,
        }

    def clear_license(self) -> None:
        """清除授权码"""
        delete_config(KEY_LICENSE_CODE)
        delete_config(KEY_LICENSE_CODE_TYPE)
        delete_config(KEY_LICENSE_EXPIRE_TIME)

    def record_first_upload(self) -> None:
        """记录首次上传时间（仅第一次）"""
        existing = get_config(KEY_FIRST_UPLOAD_TIME)
        if existing:
            return
        set_config(KEY_FIRST_UPLOAD_TIME, str(int(time.time())))
