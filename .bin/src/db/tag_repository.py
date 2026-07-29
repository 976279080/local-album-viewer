#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标签与照片标签关联数据访问层"""

import random
from typing import Dict, Any, List, Optional

from constants import TAG_COLORS
from utils import get_current_time

from .connection import _db_transaction, _db_read


@_db_transaction
def create_tag(name: str, color: str = None, **kwargs) -> int:
    """创建标签（如果已存在则返回现有ID）"""
    cursor = kwargs['cursor']
    conn = cursor.connection

    name = name.strip()
    if not name:
        raise ValueError("标签名称不能为空")

    cursor.execute('SELECT id FROM tags WHERE name = ?', (name,))
    existing = cursor.fetchone()
    if existing:
        return existing['id']

    if color is None:
        color = random.choice(TAG_COLORS)

    cursor.execute('INSERT INTO tags (name, color) VALUES (?, ?)', (name, color))

    tag_id = cursor.lastrowid

    return tag_id


@_db_read
def get_tag_by_id(tag_id: int, **kwargs) -> Optional[Dict[str, Any]]:
    """根据ID获取标签信息"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT * FROM tags WHERE id = ?', (tag_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


@_db_read
def get_tag_by_name(name: str, **kwargs) -> Optional[Dict[str, Any]]:
    """根据名称获取标签信息"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT * FROM tags WHERE name = ?', (name.strip(),))
    row = cursor.fetchone()
    return dict(row) if row else None


@_db_read
def get_all_tags(**kwargs) -> List[Dict[str, Any]]:
    """获取所有标签列表"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT * FROM tags ORDER BY name')
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


@_db_transaction
def delete_tag(tag_id: int, **kwargs) -> bool:
    """删除标签（手动删除关联）"""
    cursor = kwargs['cursor']
    conn = cursor.connection

    cursor.execute('SELECT id FROM tags WHERE id = ?', (tag_id,))
    if not cursor.fetchone():
        raise ValueError("标签不存在")

    cursor.execute('DELETE FROM photo_tags WHERE tag_id = ?', (tag_id,))
    cursor.execute('DELETE FROM tags WHERE id = ?', (tag_id,))

    return True


@_db_transaction
def cleanup_unused_tags(**kwargs) -> int:
    """清理未使用的标签（使用 NOT EXISTS 避免 NULL 问题且效率更高）"""
    cursor = kwargs['cursor']
    conn = cursor.connection

    cursor.execute('''
        DELETE FROM tags
        WHERE NOT EXISTS (SELECT 1 FROM photo_tags WHERE tag_id = tags.id)
    ''')

    return cursor.rowcount


@_db_transaction
def add_tags_to_photo(photo_id: int, tag_names: List[str], **kwargs) -> bool:
    """为照片添加标签（批量优化版）- 使用 executemany 批量插入，增量维护 tag_count"""
    cursor = kwargs['cursor']
    conn = cursor.connection

    cursor.execute('SELECT id FROM photos WHERE id = ?', (photo_id,))
    if not cursor.fetchone():
        raise ValueError("照片不存在")

    tag_names = [t.strip() for t in tag_names if t.strip()]
    if not tag_names:
        return True

    # 查询已存在的 tag id
    placeholders = ','.join(['?'] * len(tag_names))
    cursor.execute(f'SELECT name, id FROM tags WHERE name IN ({placeholders})', tag_names)
    existing_tags = {row['name']: row['id'] for row in cursor.fetchall()}

    # 批量创建新 tag（executemany）
    new_tags = [name for name in tag_names if name not in existing_tags]
    if new_tags:
        new_tag_rows = [(name, random.choice(TAG_COLORS)) for name in new_tags]
        cursor.executemany('INSERT INTO tags (name, color) VALUES (?, ?)', new_tag_rows)

        new_placeholders = ','.join(['?'] * len(new_tags))
        cursor.execute(f'SELECT name, id FROM tags WHERE name IN ({new_placeholders})', new_tags)
        for row in cursor.fetchall():
            existing_tags[row['name']] = row['id']

    # 查询当前已关联的 tag_id，避免重复 INSERT 后误增 tag_count
    cursor.execute('SELECT tag_id FROM photo_tags WHERE photo_id = ?', (photo_id,))
    already_linked = {row['tag_id'] for row in cursor.fetchall()}

    # 批量插入 photo_tags 关联（executemany）
    new_links = [(photo_id, existing_tags[name]) for name in tag_names
                 if name in existing_tags and existing_tags[name] not in already_linked]
    if new_links:
        cursor.executemany('INSERT OR IGNORE INTO photo_tags (photo_id, tag_id) VALUES (?, ?)', new_links)

    # 应用层增量维护 tag_count，避免子查询
    added_count = len(new_links)
    if added_count > 0:
        cursor.execute('UPDATE photos SET tag_count = tag_count + ?, update_time = ? WHERE id = ?',
                       (added_count, get_current_time(), photo_id))
    else:
        cursor.execute('UPDATE photos SET update_time = ? WHERE id = ?',
                       (get_current_time(), photo_id))

    return True


@_db_transaction
def remove_tags_from_photo(photo_id: int, tag_names: List[str] = None, **kwargs) -> bool:
    """从照片移除标签（不传tag_names则移除所有标签）- 应用层增量维护 tag_count"""
    cursor = kwargs['cursor']
    conn = cursor.connection

    cursor.execute('SELECT id FROM photos WHERE id = ?', (photo_id,))
    if not cursor.fetchone():
        raise ValueError("照片不存在")

    # 记录删除前的数量，用于增量更新
    cursor.execute('SELECT COUNT(*) as cnt FROM photo_tags WHERE photo_id = ?', (photo_id,))
    before_count = cursor.fetchone()['cnt']

    if tag_names:
        # 批量查询 tag_ids，避免 N 次 SELECT
        placeholders = ','.join(['?'] * len(tag_names))
        cursor.execute(f'SELECT id FROM tags WHERE name IN ({placeholders})', tag_names)
        tag_ids = [row['id'] for row in cursor.fetchall()]
        if tag_ids:
            ph = ','.join(['?'] * len(tag_ids))
            cursor.execute(
                f'DELETE FROM photo_tags WHERE photo_id = ? AND tag_id IN ({ph})',
                [photo_id] + tag_ids
            )
    else:
        cursor.execute('DELETE FROM photo_tags WHERE photo_id = ?', (photo_id,))

    # 计算删除后的数量，增量更新 tag_count
    cursor.execute('SELECT COUNT(*) as cnt FROM photo_tags WHERE photo_id = ?', (photo_id,))
    after_count = cursor.fetchone()['cnt']
    delta = before_count - after_count
    if delta != 0:
        cursor.execute('UPDATE photos SET tag_count = ?, update_time = ? WHERE id = ?',
                       (after_count, get_current_time(), photo_id))
    else:
        cursor.execute('UPDATE photos SET update_time = ? WHERE id = ?',
                       (get_current_time(), photo_id))

    return True


@_db_read
def get_photo_tags(photo_id: int, **kwargs) -> List[Dict[str, Any]]:
    """获取照片的所有标签"""
    cursor = kwargs['cursor']
    cursor.execute('''
        SELECT t.* FROM tags t
        JOIN photo_tags pt ON t.id = pt.tag_id
        WHERE pt.photo_id = ?
        ORDER BY t.name
    ''', (photo_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


@_db_transaction
def batch_add_tags_to_photos(photo_ids: List[int], tag_names: List[str], **kwargs) -> None:
    """批量为多张照片添加标签（单事务，避免 N+1）"""
    cursor = kwargs['cursor']
    conn = cursor.connection

    tag_names = [t.strip() for t in tag_names if t.strip()]
    if not tag_names or not photo_ids:
        return

    placeholders = ','.join(['?'] * len(tag_names))
    cursor.execute(f'SELECT name, id FROM tags WHERE name IN ({placeholders})', tag_names)
    existing_tags = {row['name']: row['id'] for row in cursor.fetchall()}

    new_tags = [name for name in tag_names if name not in existing_tags]
    if new_tags:
        new_tag_rows = [(name, random.choice(TAG_COLORS)) for name in new_tags]
        cursor.executemany('INSERT INTO tags (name, color) VALUES (?, ?)', new_tag_rows)
        cursor.execute(f'SELECT name, id FROM tags WHERE name IN ({placeholders})', new_tags)
        for row in cursor.fetchall():
            existing_tags[row['name']] = row['id']

    tag_ids = [existing_tags[name] for name in tag_names if name in existing_tags]
    photo_placeholders = ','.join(['?'] * len(photo_ids))
    tag_placeholders = ','.join(['?'] * len(tag_ids))
    cursor.execute(f'''
        SELECT photo_id, tag_id FROM photo_tags
        WHERE photo_id IN ({photo_placeholders}) AND tag_id IN ({tag_placeholders})
    ''', photo_ids + tag_ids)
    existing_links = {(row['photo_id'], row['tag_id']) for row in cursor.fetchall()}

    new_links = [(pid, tid) for pid in photo_ids for tid in tag_ids
                 if (pid, tid) not in existing_links]
    if new_links:
        cursor.executemany('INSERT OR IGNORE INTO photo_tags (photo_id, tag_id) VALUES (?, ?)', new_links)

    added_per_photo = len(new_links) // len(photo_ids) if photo_ids else 0
    if added_per_photo > 0:
        cursor.execute(f'UPDATE photos SET tag_count = tag_count + ?, update_time = ? WHERE id IN ({photo_placeholders})',
                       (added_per_photo, get_current_time()) + tuple(photo_ids))
    else:
        cursor.execute(f'UPDATE photos SET update_time = ? WHERE id IN ({photo_placeholders})',
                       (get_current_time(),) + tuple(photo_ids))


@_db_transaction
def batch_remove_tags_from_photos(photo_ids: List[int], **kwargs) -> None:
    """批量移除多张照片的所有标签（单事务，避免 N+1）"""
    cursor = kwargs['cursor']

    if not photo_ids:
        return

    placeholders = ','.join(['?'] * len(photo_ids))

    cursor.execute(f'''
        SELECT pt.photo_id, pt.tag_id FROM photo_tags pt
        JOIN photos p ON pt.photo_id = p.id
        WHERE pt.photo_id IN ({placeholders})
    ''', tuple(photo_ids))
    existing_links = cursor.fetchall()

    if existing_links:
        cursor.execute(f'DELETE FROM photo_tags WHERE photo_id IN ({placeholders})', tuple(photo_ids))

        tag_counts = {}
        for row in existing_links:
            tag_counts[row['photo_id']] = tag_counts.get(row['photo_id'], 0) + 1

        for pid, cnt in tag_counts.items():
            cursor.execute('UPDATE photos SET tag_count = MAX(0, tag_count - ?), update_time = ? WHERE id = ?',
                          (cnt, get_current_time(), pid))
    else:
        cursor.execute(f'UPDATE photos SET update_time = ? WHERE id IN ({placeholders})',
                       (get_current_time(),) + tuple(photo_ids))


@_db_read
def batch_get_photo_tags(photo_ids: List[int], **kwargs) -> Dict[int, List[str]]:
    """批量获取照片的标签名称（单次查询，避免 N+1）"""
    cursor = kwargs['cursor']
    if not photo_ids:
        return {}

    from constants import TAG_BATCH_SIZE
    tags_map = {}

    for i in range(0, len(photo_ids), TAG_BATCH_SIZE):
        batch = photo_ids[i:i + TAG_BATCH_SIZE]
        placeholders = ','.join(['?'] * len(batch))
        cursor.execute(f'''
            SELECT pt.photo_id, t.name
            FROM photo_tags pt
            JOIN tags t ON pt.tag_id = t.id
            WHERE pt.photo_id IN ({placeholders})
            ORDER BY t.name
        ''', batch)
        for row in cursor.fetchall():
            pid = row['photo_id']
            tags_map.setdefault(pid, []).append(row['name'])

    return tags_map
