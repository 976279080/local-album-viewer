#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""认证中间件 - 纯函数式认证校验"""

from utils.auth_util import load_password


def check_auth(headers) -> bool:
    """检查请求头中的密码认证

    Args:
        headers: HTTP 请求头对象（需支持 .get 方法）

    Returns:
        True 表示认证通过
    """
    auth = headers.get('X-Auth', '')
    return auth == load_password()
