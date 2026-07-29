#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""系统配置数据访问层"""

from typing import Dict, Optional

from utils import get_current_time

from .connection import _db_transaction, _db_read


@_db_read
def get_config(key: str, **kwargs) -> Optional[str]:
    """获取单个配置"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT value FROM system_config WHERE key = ?', (key,))
    row = cursor.fetchone()
    return row['value'] if row else None


@_db_transaction
def set_config(key: str, value: str, **kwargs) -> None:
    """设置配置（存在则更新）"""
    cursor = kwargs['cursor']
    now = get_current_time()
    cursor.execute('''
        INSERT INTO system_config (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
    ''', (key, value, now))


@_db_read
def get_all_config(**kwargs) -> Dict[str, str]:
    """获取所有配置"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT key, value FROM system_config')
    rows = cursor.fetchall()
    return {row['key']: row['value'] for row in rows}


@_db_transaction
def delete_config(key: str, **kwargs) -> None:
    """删除配置"""
    cursor = kwargs['cursor']
    cursor.execute('DELETE FROM system_config WHERE key = ?', (key,))
