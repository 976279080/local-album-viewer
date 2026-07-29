#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""授权配置读取 - 从 system_config 表读取授权相关配置

代码运行时不持有任何明文密钥/天数常量，统一从数据库读取。
默认值由 db.schema._seed_license_config 在首次初始化时写入。
"""

from db import get_config


def get_license_secret_key() -> str:
    """获取授权码签名密钥"""
    return get_config('license_secret_key') or ''


def get_free_trial_days() -> int:
    """获取免费试用期天数"""
    val = get_config('free_trial_days')
    try:
        return int(val) if val is not None else 0
    except ValueError:
        return 0


def get_license_monthly_days() -> int:
    """获取月卡有效期天数"""
    val = get_config('license_monthly_days')
    try:
        return int(val) if val is not None else 0
    except ValueError:
        return 0


def get_license_yearly_days() -> int:
    """获取年卡有效期天数"""
    val = get_config('license_yearly_days')
    try:
        return int(val) if val is not None else 0
    except ValueError:
        return 0
