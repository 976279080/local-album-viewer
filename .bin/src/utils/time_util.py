#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时间相关工具函数"""

from datetime import datetime
from typing import Optional


def get_current_time() -> int:
    """获取当前时间的Unix时间戳（秒）"""
    return int(datetime.now().timestamp())


def format_datetime(dt_str: Optional[str]) -> str:
    """格式化日期时间字符串

    Args:
        dt_str: ISO格式的日期时间字符串

    Returns:
        格式化后的日期时间字符串
    """
    if not dt_str:
        return ''

    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return dt_str


def parse_iso_to_timestamp(dt_str: str) -> Optional[int]:
    """将 ISO 格式时间字符串解析为 Unix 时间戳

    兼容 JavaScript ISO 格式（带 Z 后缀和毫秒），Python 3.9 不直接支持。

    Args:
        dt_str: ISO 格式时间字符串

    Returns:
        Unix 时间戳（秒），解析失败返回 None
    """
    if not dt_str:
        return None
    try:
        ct_str = dt_str.replace('Z', '+00:00')
        return int(datetime.fromisoformat(ct_str).timestamp())
    except Exception:
        return None
