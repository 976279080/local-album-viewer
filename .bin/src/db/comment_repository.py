#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评论数据访问层"""

from typing import Dict, Any, List

from constants import MAX_COMMENT_LENGTH
from utils import get_current_time

from .connection import _db_transaction, _db_read


@_db_transaction
def add_comment(photo_id: int, text: str, **kwargs) -> int:
    """为照片添加评论"""
    cursor = kwargs['cursor']

    cursor.execute('SELECT id FROM photos WHERE id = ?', (photo_id,))
    if not cursor.fetchone():
        raise ValueError("照片不存在")

    text = text.strip()[:MAX_COMMENT_LENGTH]
    if not text:
        raise ValueError("评论内容不能为空")

    cursor.execute('''
        INSERT INTO comments (photo_id, text, created_at)
        VALUES (?, ?, ?)
    ''', (photo_id, text, get_current_time()))

    cursor.execute('UPDATE photos SET comment_count = comment_count + 1, update_time = ? WHERE id = ?',
                   (get_current_time(), photo_id))

    return cursor.lastrowid


@_db_transaction
def delete_comment(comment_id: int, **kwargs) -> bool:
    """删除评论"""
    cursor = kwargs['cursor']

    cursor.execute('SELECT photo_id FROM comments WHERE id = ?', (comment_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("评论不存在")

    photo_id = row['photo_id']

    cursor.execute('DELETE FROM comments WHERE id = ?', (comment_id,))

    cursor.execute('UPDATE photos SET comment_count = comment_count - 1, update_time = ? WHERE id = ?',
                   (get_current_time(), photo_id))

    return True


@_db_read
def get_photo_comments(photo_id: int, **kwargs) -> List[Dict[str, Any]]:
    """获取照片的所有评论"""
    cursor = kwargs['cursor']
    cursor.execute('''
        SELECT * FROM comments WHERE photo_id = ?
        ORDER BY created_at DESC
    ''', (photo_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


@_db_transaction
def delete_all_comments(photo_id: int, **kwargs) -> None:
    """删除照片的所有评论"""
    cursor = kwargs['cursor']
    cursor.execute('DELETE FROM comments WHERE photo_id = ?', (photo_id,))
    cursor.execute('UPDATE photos SET comment_count = 0, update_time = ? WHERE id = ?',
                   (get_current_time(), photo_id))


@_db_transaction
def batch_add_comments(photo_id: int, texts: List[str], **kwargs) -> None:
    """批量添加评论（executemany，避免循环单条 INSERT）"""
    cursor = kwargs['cursor']

    cursor.execute('SELECT id FROM photos WHERE id = ?', (photo_id,))
    if not cursor.fetchone():
        raise ValueError("照片不存在")

    now = get_current_time()
    valid_texts = [t.strip()[:MAX_COMMENT_LENGTH] for t in texts if t.strip()]
    if not valid_texts:
        return

    cursor.executemany('INSERT INTO comments (photo_id, text, created_at) VALUES (?, ?, ?)',
                       [(photo_id, text, now) for text in valid_texts])

    cursor.execute('UPDATE photos SET comment_count = comment_count + ?, update_time = ? WHERE id = ?',
                   (len(valid_texts), now, photo_id))
