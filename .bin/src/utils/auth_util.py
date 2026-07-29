#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""认证工具函数"""

from config import PASSWORD


def load_password() -> str:
    """返回访问密码（来自 config.py）

    Returns:
        密码字符串
    """
    return PASSWORD


def verify_password(pwd: str) -> bool:
    """校验密码是否正确

    Args:
        pwd: 待校验的密码

    Returns:
        True 表示密码正确
    """
    return pwd == PASSWORD
