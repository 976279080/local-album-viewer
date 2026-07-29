#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计概览数据访问层"""

from typing import Dict, Any, List

from .connection import _db_read


@_db_read
def get_summary(**kwargs) -> Dict[str, Any]:
    """获取相册和标签概览"""
    # 延迟导入避免与 photo_repository 循环依赖
    from .photo_repository import get_photo_count

    cursor = kwargs['cursor']

    # 直接使用 albums.latest_upload 字段（应用层维护，避免聚合查询）
    cursor.execute('''
        SELECT id, name, color, latest_upload
        FROM albums a
        ORDER BY CASE WHEN a.latest_upload IS NULL OR a.latest_upload = 0 THEN 1 ELSE 0 END,
                 a.latest_upload DESC,
                 a.name
    ''')
    albums = cursor.fetchall()

    cursor.execute('SELECT * FROM tags ORDER BY name')
    tags = cursor.fetchall()

    counts = get_photo_count()

    summary = {
        'members': {a['id']: {'name': a['name'], 'color': a['color']} for a in albums},
        'album_order': [a['id'] for a in albums],
        'tags': {t['name']: {'color': t['color']} for t in tags},
        'counts': counts
    }

    return summary


@_db_read
def get_years(**kwargs) -> List[tuple]:
    """获取所有年份列表"""
    cursor = kwargs['cursor']
    cursor.execute('''
        SELECT year, COUNT(*) as cnt FROM photos
        GROUP BY year ORDER BY year DESC
    ''')
    rows = cursor.fetchall()
    return [(row['year'], row['cnt']) for row in rows]
