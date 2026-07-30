#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""认证中间件 - 纯函数式认证校验

支持两种方式：
  1. X-Auth 请求头 = 正式密码
  2. X-Auth 请求头 = 临时 token（扫码上传用，1 小时内有效）
"""

import secrets
import time
from typing import Optional, Dict

from utils.auth_util import load_password

# 内存中保存临时上传 token：{ token: expires_at_timestamp }
_MOBILE_TOKENS: Dict[str, int] = {}
TOKEN_TTL_SECONDS = 3600  # 1 小时有效期


def create_upload_token() -> str:
    """生成新的手机端上传 token（自动清理过期）"""
    # 清理过期 token
    now = int(time.time())
    expired_keys = [k for k, v in _MOBILE_TOKENS.items() if v < now]
    for k in expired_keys:
        _MOBILE_TOKENS.pop(k, None)

    token = secrets.token_hex(16)
    _MOBILE_TOKENS[token] = now + TOKEN_TTL_SECONDS
    return token


def _is_valid_token(auth: str) -> bool:
    """检查是否为有效临时上传 token"""
    if not auth:
        return False
    now = int(time.time())
    expires = _MOBILE_TOKENS.get(auth)
    if expires and expires >= now:
        return True
    # 顺带清理过期
    expired_keys = [k for k, v in _MOBILE_TOKENS.items() if v < now]
    for k in expired_keys:
        _MOBILE_TOKENS.pop(k, None)
    return False


def check_auth(headers) -> bool:
    """检查请求认证（密码或 token）

    Args:
        headers: HTTP 请求头对象（需支持 .get 方法）

    Returns:
        True 表示认证通过
    """
    auth = headers.get('X-Auth', '')
    if not auth:
        # 支持 query 参数传 token（手机端 file input 表单无自定义 header）
        referer = headers.get('Referer', '') or ''
        # referer 解析太麻烦，上传端会用 header 传，这里先只看 header
        return False
    if auth == load_password():
        return True
    return _is_valid_token(auth)
