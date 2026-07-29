#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""相册数据访问层 - 仅负责数据库操作，不涉及文件系统"""

import random
from typing import Dict, Any, List, Optional

from constants import ALBUM_COLORS
from utils import get_current_time, validate_album_name

from .connection import (
    _db_transaction, _db_read, _execute_with_lock, get_db_connection,
)


@_db_transaction
def create_album(name: str, color: str = None, **kwargs) -> int:
    """创建相册，返回相册ID（不创建磁盘目录，由 service 层负责）"""
    cursor = kwargs['cursor']

    validate_album_name(name)
    name = name.strip()

    cursor.execute('SELECT id FROM albums WHERE name = ?', (name,))
    if cursor.fetchone():
        raise ValueError("相册已存在")

    if color is None:
        color = random.choice(ALBUM_COLORS)

    now = get_current_time()
    cursor.execute('''
        INSERT INTO albums (name, color, created_at, updated_at)
        VALUES (?, ?, ?, ?)
    ''', (name, color, now, now))

    return cursor.lastrowid


@_db_read
def get_album_by_id(album_id: int, **kwargs) -> Optional[Dict[str, Any]]:
    """根据ID获取相册信息"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT * FROM albums WHERE id = ?', (album_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


@_db_read
def get_album_by_name(name: str, **kwargs) -> Optional[Dict[str, Any]]:
    """根据原始名称获取相册信息"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT * FROM albums WHERE name = ?', (name.strip(),))
    row = cursor.fetchone()
    return dict(row) if row else None


@_db_read
def get_all_albums(**kwargs) -> List[Dict[str, Any]]:
    """获取所有相册列表"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT * FROM albums ORDER BY name')
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


@_db_transaction
def update_album(album_id: int, name: str = None, color: str = None, **kwargs) -> bool:
    """更新相册信息"""
    cursor = kwargs['cursor']

    cursor.execute('SELECT * FROM albums WHERE id = ?', (album_id,))
    album = cursor.fetchone()
    if not album:
        raise ValueError("相册不存在")

    updates = []
    params = []

    if name is not None:
        validate_album_name(name)
        name = name.strip()

        cursor.execute('''
            SELECT id FROM albums WHERE name = ? AND id != ?
        ''', (name, album_id))
        if cursor.fetchone():
            raise ValueError("相册已存在")

        updates.append('name = ?')
        params.append(name)

    if color is not None:
        updates.append('color = ?')
        params.append(color)

    if updates:
        updates.append('updated_at = ?')
        params.append(get_current_time())
        params.append(album_id)

        sql = f'UPDATE albums SET {", ".join(updates)} WHERE id = ?'
        cursor.execute(sql, params)

    return True


@_db_transaction
def rename_album_records(album_id: int, new_name: str, **kwargs) -> Dict[str, Any]:
    """重命名相册的数据库记录（不操作文件系统）

    Returns:
        包含 old_name 和 photos 列表的字典，供 service 层执行文件重命名
    """
    cursor = kwargs['cursor']

    cursor.execute('SELECT * FROM albums WHERE id = ?', (album_id,))
    album = cursor.fetchone()
    if not album:
        raise ValueError("相册不存在")

    old_name = album['name']

    validate_album_name(new_name)
    new_name = new_name.strip()

    if new_name == old_name:
        return {'old_name': old_name, 'new_name': new_name, 'photos': [], 'skipped': True}

    cursor.execute('SELECT id FROM albums WHERE name = ? AND id != ?', (new_name, album_id))
    if cursor.fetchone():
        raise ValueError("相册已存在")

    now = get_current_time()
    cursor.execute('UPDATE albums SET name = ?, updated_at = ? WHERE id = ?',
                   (new_name, now, album_id))

    cursor.execute('SELECT id, filename, year FROM photos WHERE album_id = ?', (album_id,))
    photos = [dict(row) for row in cursor.fetchall()]

    return {'old_name': old_name, 'new_name': new_name, 'photos': photos, 'skipped': False}


@_db_transaction
def delete_album_records(album_id: int, **kwargs) -> Dict[str, Any]:
    """删除相册的所有数据库记录（不操作文件系统）

    Returns:
        包含 name 和 photos 列表的字典，供 service 层清理文件
    """
    cursor = kwargs['cursor']

    cursor.execute('SELECT name FROM albums WHERE id = ?', (album_id,))
    album = cursor.fetchone()
    if not album:
        raise ValueError("相册不存在")

    name = album['name']

    cursor.execute('SELECT id, filename, year FROM photos WHERE album_id = ?', (album_id,))
    photos = [dict(row) for row in cursor.fetchall()]

    cursor.execute('DELETE FROM comments WHERE photo_id IN (SELECT id FROM photos WHERE album_id = ?)', (album_id,))
    cursor.execute('DELETE FROM photo_tags WHERE photo_id IN (SELECT id FROM photos WHERE album_id = ?)', (album_id,))
    cursor.execute('DELETE FROM photos WHERE album_id = ?', (album_id,))
    cursor.execute('DELETE FROM albums WHERE id = ?', (album_id,))

    return {'name': name, 'photos': photos}
